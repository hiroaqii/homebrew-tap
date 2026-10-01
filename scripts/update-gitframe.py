#!/usr/bin/env python3
"""Create or resume a GitFrame Formula update PR, then wait for Install checks."""

import argparse
import base64
import difflib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import quote, urlencode


ROOT = Path(__file__).resolve().parent.parent
SOURCE = "hiroaqii/gitframe"
TAP = "hiroaqii/homebrew-tap"
FORMULA = "Formula/gitframe.rb"
PLATFORMS = {"on_macos": "macos-arm64", "on_linux": "linux-x86_64"}
INSTALL_JOBS = {f"Install ({os})" for os in ("ubuntu-22.04", "macos-15", "macos-26")}
VERSION_PATTERN = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"


def command(*args, cwd=ROOT, check=True):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"{args[0]} failed")
    return result


def api(repo, path, *, data=None, missing_ok=False, raw=False):
    args = ["gh", "api", "--hostname", "github.com", f"repos/{repo}/{path}"]
    if raw:
        args += ["-H", "Accept: application/octet-stream"]
    if data is not None:
        args += ["--method", "POST", "--input", "-"]
    result = subprocess.run(args, cwd=ROOT, input=json.dumps(data) if data is not None else None,
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        if missing_ok and "(HTTP 404)" in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout if raw else json.loads(result.stdout or "null")


def version_tuple(value):
    if not re.fullmatch(VERSION_PATTERN, value):
        raise ValueError("Use a stable major.minor.patch version, without a v prefix.")
    return tuple(map(int, value.split(".")))


def release_hashes(version):
    tag = f"v{version}"
    value = api(SOURCE, f"releases/tags/{tag}")
    if value["draft"] or value["prerelease"] or value["tag_name"] != tag:
        raise ValueError(f"{tag} must be a published stable release")
    expected = {f"gitframe-{tag}-{platform}.tar.gz" for platform in PLATFORMS.values()}
    names = expected | {"SHA256SUMS"}
    assets = [asset for asset in value["assets"] if asset["name"] in names]
    if len(assets) != len(names) or {asset["name"] for asset in assets} != names:
        raise ValueError("Release must contain both archives and SHA256SUMS exactly once.")
    if any(asset["state"] != "uploaded" or asset["size"] <= 0 for asset in assets):
        raise ValueError("Release contains incomplete or empty assets.")
    assets = {asset["name"]: asset for asset in assets}
    contents = api(SOURCE, f"releases/assets/{assets['SHA256SUMS']['id']}", raw=True)
    hashes = {}
    for line in contents.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (\S+)", line)
        if match is None or match[2] in hashes:
            raise ValueError("Invalid or duplicate entry in SHA256SUMS")
        hashes[match[2]] = match[1]
    if set(hashes) != expected:
        raise ValueError("SHA256SUMS does not match the expected release archives")
    for name, digest in hashes.items():
        if assets[name].get("digest") != f"sha256:{digest}":
            raise ValueError(f"GitHub asset digest does not match SHA256SUMS: {name}")
    return {platform: hashes[f"gitframe-{tag}-{platform}.tar.gz"] for platform in PLATFORMS.values()}


def update_formula(text, version, hashes):
    new_version = version_tuple(version)
    versions = list(re.finditer(r'^  version "([^"\n]+)"$', text, re.M))
    if len(versions) != 1:
        raise ValueError("Expected exactly one Formula version line")
    previous = versions[0][1]
    if new_version < version_tuple(previous):
        raise ValueError(f"Refusing to downgrade Formula from {previous} to {version}")
    result = text[:versions[0].start(1)] + version + text[versions[0].end(1):]
    for block, platform in PLATFORMS.items():
        digest = hashes.get(platform, "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid SHA-256 for {platform}")
        sections = list(re.finditer(rf"^  {block} do\n(.*?)^  end$", result, re.M | re.S))
        if len(sections) != 1:
            raise ValueError(f"Expected exactly one {block} block")
        section = sections[0]
        expected_url = (f'    url "https://github.com/{SOURCE}/releases/download/v#{{version}}/'
                        f'gitframe-v#{{version}}-{platform}.tar.gz"')
        if section[1].splitlines().count(expected_url) != 1:
            raise ValueError(f"Unexpected release URL in {block}")
        sha_lines = list(re.finditer(r'^    sha256 "([0-9a-f]{64})"$', section[1], re.M))
        if len(sha_lines) != 1:
            raise ValueError(f"Expected exactly one SHA-256 in {block}")
        sha = sha_lines[0]
        start, end = section.start(1) + sha.start(1), section.start(1) + sha.end(1)
        result = result[:start] + digest + result[end:]
    if previous == version and result != text:
        raise ValueError("This version is already in the Formula with different hashes; inspect it manually.")
    return result


def formula_at(sha):
    value = api(TAP, f"contents/{FORMULA}?{urlencode({'ref': sha})}")
    if value["encoding"] != "base64":
        raise ValueError("Unexpected Formula encoding")
    return base64.b64decode(value["content"]).decode("utf-8")


def find_pr(branch):
    query = urlencode({"state": "all", "head": f"hiroaqii:{branch}", "base": "main", "per_page": 100})
    matches = api(TAP, f"pulls?{query}")
    if len(matches) > 1:
        raise ValueError(f"Multiple PRs found for {branch}; inspect them manually.")
    if not matches:
        return None
    pr = matches[0]
    if pr["head"]["repo"]["full_name"] != TAP or pr["head"]["ref"] != branch or pr["base"]["ref"] != "main":
        raise ValueError("Existing PR has an unexpected source or target branch")
    if pr["state"] != "open":
        raise ValueError(f"Existing PR is closed but main does not contain the requested Formula: {pr['html_url']}")
    return pr


def validate_branch(base_sha, head_sha, expected):
    comparison = api(TAP, f"compare/{base_sha}...{head_sha}")
    files = comparison.get("files", [])
    if len(files) != 1 or files[0]["filename"] != FORMULA or files[0]["status"] != "modified":
        raise ValueError("Existing update branch must change only Formula/gitframe.rb; it will not be overwritten.")
    if formula_at(head_sha) != expected:
        raise ValueError("Existing update branch differs from the expected Formula; it will not be overwritten.")


def create_branch(branch, base_sha, expected, version):
    # Keep the user's checkout and branch untouched. Authentication is scoped to these commands.
    credentials = ("git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential")
    with tempfile.TemporaryDirectory(prefix="gitframe-tap-update-") as temporary:
        checkout = Path(temporary) / "tap"
        command(*credentials, "clone", "--quiet", "--no-checkout", f"https://github.com/{TAP}.git", str(checkout))
        command("git", "switch", "--create", branch, base_sha, cwd=checkout)
        (checkout / FORMULA).write_text(expected)
        command("ruby", "-c", FORMULA, cwd=checkout)
        command("git", "diff", "--check", cwd=checkout)
        command("git", "add", "--", FORMULA, cwd=checkout)
        command("git", "commit", "-m", f"gitframe: update to {version}", cwd=checkout)
        sha = command("git", "rev-parse", "HEAD", cwd=checkout).stdout.strip()
        command(*credentials, "push", "origin", f"HEAD:refs/heads/{branch}", cwd=checkout)
        return sha


def wait_for_install(pr, head_sha, timeout):
    deadline = time.monotonic() + timeout
    last_status = None
    while True:
        current = api(TAP, f"pulls/{pr['number']}")
        if current["head"]["sha"] != head_sha:
            raise ValueError("PR changed while waiting for Install checks; rerun to validate the new contents.")
        if current["state"] == "closed" and not current.get("merged"):
            raise ValueError("PR was closed without merging")
        result = command("gh", "pr", "checks", str(pr["number"]), "--repo", TAP,
                         "--json", "name,bucket,workflow,link", check=False)
        if result.returncode not in (0, 1, 8):
            raise RuntimeError(result.stderr.strip() or "Could not retrieve PR checks")
        try:
            checks = json.loads(result.stdout)
        except json.JSONDecodeError:
            if result.returncode == 1 and "no checks reported" in result.stderr.lower():
                checks = []
            else:
                raise RuntimeError(result.stderr.strip() or "Could not retrieve PR checks") from None
        checks = [check for check in checks if check["workflow"] == "Install"]
        status = sorted((check["name"], check["bucket"]) for check in checks)
        if status != last_status:
            print(f"{pr['html_url']}: {status or 'waiting for Install checks'}", flush=True)
            last_status = status
        failed = [check for check in checks if check["bucket"] not in ("pass", "pending")]
        if failed:
            raise RuntimeError(f"Install did not pass: {failed[0]['link']}. Rerun failed checks in Actions, then rerun this script.")
        names = {check["name"] for check in checks}
        if len(names) == len(checks) and INSTALL_JOBS <= names and all(
                check["bucket"] == "pass" for check in checks):
            run_ids = [re.search(r"/actions/runs/([0-9]+)/", check["link"]) for check in checks]
            if any(match is None for match in run_ids) or len({match[1] for match in run_ids}) != 1:
                raise ValueError("Install checks do not belong to one workflow run; inspect Actions before merging.")
            final = api(TAP, f"pulls/{pr['number']}")
            if final["head"]["sha"] != head_sha:
                raise ValueError("PR changed while checking results")
            if final["state"] == "closed" and not final.get("merged"):
                raise ValueError("PR was closed without merging")
            action = "Already merged" if final.get("merged") else "Review and merge"
            print(f"Install checks passed on all three platforms. {action}: {pr['html_url']}", flush=True)
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Still waiting for Install checks: {pr['html_url']}. Rerun to resume.")
        time.sleep(10)


def run(args):
    version_tuple(args.version)
    origin = command("git", "remote", "get-url", "origin").stdout.strip()
    if origin.removesuffix(".git") not in (f"git@github.com:{TAP}", f"https://github.com/{TAP}"):
        raise ValueError(f"origin must point to {TAP}")
    hashes = release_hashes(args.version)
    base_sha = api(TAP, "git/ref/heads/main")["object"]["sha"]
    previous = formula_at(base_sha)
    expected = update_formula(previous, args.version, hashes)
    if previous == expected:
        print(f"main already contains GitFrame {args.version} with the published hashes. No update needed.")
        return
    # Validate before creating any branch, commit, or PR, including dry runs.
    with tempfile.TemporaryDirectory(prefix="gitframe-formula-check-") as temporary:
        path = Path(temporary) / "gitframe.rb"
        path.write_text(expected)
        command("ruby", "-c", str(path))
    print("".join(difflib.unified_diff(previous.splitlines(True), expected.splitlines(True),
                                     fromfile=FORMULA, tofile=FORMULA)), end="", flush=True)
    branch = f"chore/gitframe-{args.version}"
    pr = find_pr(branch)
    ref = api(TAP, f"git/ref/heads/{quote(branch, safe='/')}", missing_ok=True)
    head_sha = ref["object"]["sha"] if ref else None
    if head_sha:
        validate_branch(base_sha, head_sha, expected)
    if pr and pr["head"]["sha"] != head_sha:
        raise ValueError("Existing PR and branch do not agree; retry after checking their state.")
    if args.dry_run:
        print(f"Would reuse {pr['html_url']} and wait for Install." if pr else
              f"Would {'reuse' if head_sha else 'create/push'} {branch}, create a PR, and wait for Install.")
        return
    if head_sha is None:
        head_sha = create_branch(branch, base_sha, expected, args.version)
    if pr is None:
        pr = api(TAP, "pulls", data={
            "title": f"gitframe: update to {args.version}", "head": branch, "base": "main",
            "body": f"Update GitFrame to [{args.version}](https://github.com/{SOURCE}/releases/tag/v{args.version}) "
                    "using the published SHA256SUMS, verified against GitHub asset digests.\n\n"
                    "Validation: Ruby syntax check passed. The Install workflow checks Homebrew and mise "
                    "on Ubuntu 22.04, macOS 15, and macOS 26 before merge.\n",
        })
    print(f"Update PR: {pr['html_url']}", flush=True)
    wait_for_install(pr, head_sha, args.timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="published stable version, without v (for example: 0.1.2)")
    parser.add_argument("--dry-run", action="store_true", help="show the diff without creating a branch, commit, or PR")
    parser.add_argument("--timeout", type=int, default=1800, help="seconds to wait for Install checks (default: 1800)")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        run(args)
    except (ValueError, RuntimeError, OSError, TimeoutError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"update-gitframe: {error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Stopped waiting. The PR and Actions remain available; rerun to resume.\n")


if __name__ == "__main__":
    main()
