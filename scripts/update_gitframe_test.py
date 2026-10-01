"""Formula update tests use fake GitHub responses and temporary local Git repos."""

import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("update_gitframe", Path(__file__).with_name("update-gitframe.py"))
tap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tap)
SHA = "a" * 40
HEAD = "b" * 40
VERSION = "1.2.3"
HASHES = {"macos-arm64": "1" * 64, "linux-x86_64": "2" * 64}
FORMULA = '''class Gitframe < Formula
  version "1.2.2"
  # Keep unrelated content intact.
  on_macos do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-macos-arm64.tar.gz"
    sha256 "MAC_HASH"
    depends_on arch: :arm64
  end
  on_linux do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-linux-x86_64.tar.gz"
    sha256 "LINUX_HASH"
    depends_on arch: :x86_64
  end
end
'''.replace("MAC_HASH", "a" * 64).replace("LINUX_HASH", "b" * 64)
PR = {"number": 7, "html_url": "https://github.com/hiroaqii/homebrew-tap/pull/7", "state": "open",
      "head": {"sha": HEAD, "ref": "chore/gitframe-1.2.3", "repo": {"full_name": tap.TAP}},
      "base": {"ref": "main"}}


def release_fixture():
    assets = [{"name": f"gitframe-v{VERSION}-{platform}.tar.gz", "digest": f"sha256:{digest}",
               "id": index, "size": 20, "state": "uploaded"}
              for index, (platform, digest) in enumerate(HASHES.items(), 1)]
    sums = "".join(f"{asset['digest'][7:]}  {asset['name']}\n" for asset in assets)
    assets.append({"name": "SHA256SUMS", "id": 3, "size": len(sums), "state": "uploaded"})
    return {"tag_name": f"v{VERSION}", "draft": False, "prerelease": False, "assets": assets}, sums


def checks(bucket="pass"):
    return [{"name": name, "workflow": "Install", "bucket": bucket,
             "link": f"https://github.com/{tap.TAP}/actions/runs/123/job/{index}"}
            for index, name in enumerate(sorted(tap.INSTALL_JOBS))]


class FormulaTests(unittest.TestCase):
    def args(self, **changes):
        args = argparse.Namespace(version=VERSION, timeout=30, dry_run=False)
        for key, value in changes.items():
            setattr(args, key, value)
        return args

    def test_changes_only_the_version_and_two_hashes(self):
        result = tap.update_formula(FORMULA, VERSION, HASHES)
        self.assertEqual(result, FORMULA.replace('version "1.2.2"', 'version "1.2.3"')
                         .replace("a" * 64, HASHES["macos-arm64"]).replace("b" * 64, HASHES["linux-x86_64"]))
        self.assertEqual(tap.update_formula(result, VERSION, HASHES), result)

    def test_rejects_downgrades_and_replacing_hashes_of_the_same_version(self):
        with self.assertRaisesRegex(ValueError, "downgrade"):
            tap.update_formula(FORMULA, "1.2.1", HASHES)
        with self.assertRaisesRegex(ValueError, "different hashes"):
            tap.update_formula(FORMULA, "1.2.2", HASHES)

    def test_rejects_unexpected_formula_layout_before_modifying_any_file(self):
        invalid = [FORMULA.replace('  version "1.2.2"', ''),
                   FORMULA.replace('  version "1.2.2"', '  version "1.2.2"\n  version "1.2.2"'),
                   FORMULA.replace("on_linux do", "on_freebsd do"),
                   FORMULA.replace("releases/download", "other/download"),
                   FORMULA.replace('    sha256 "' + "a" * 64 + '"', '    sha256 "invalid"')]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                tap.update_formula(value, VERSION, HASHES)

    def test_version_must_be_stable_and_is_compared_numerically(self):
        for version in ("v1.2.3", "1.2", "1.2.3-rc.1", "01.2.3", "1.2.3\n"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                tap.version_tuple(version)
        self.assertIn('version "1.10.0"', tap.update_formula(FORMULA, "1.10.0", HASHES))

    def test_downloaded_checksums_match_both_github_asset_digests(self):
        value, sums = release_fixture()
        with patch.object(tap, "api", side_effect=[value, sums]):
            self.assertEqual(tap.release_hashes(VERSION), HASHES)
        for mutation in ("draft", "missing", "duplicate", "empty", "digest"):
            changed = copy.deepcopy(value)
            if mutation == "draft":
                changed["draft"] = True
            elif mutation == "missing":
                changed["assets"].pop(0)
            elif mutation == "duplicate":
                changed["assets"].append(changed["assets"][0])
            elif mutation == "empty":
                changed["assets"][0]["size"] = 0
            else:
                changed["assets"][0]["digest"] = "sha256:" + "f" * 64
            with self.subTest(mutation=mutation), patch.object(tap, "api", side_effect=[changed, sums]):
                with self.assertRaises(ValueError):
                    tap.release_hashes(VERSION)
        for invalid in (sums + sums, "garbage", sums.replace("1" * 64, "1" * 63)):
            with self.subTest(invalid=invalid), patch.object(tap, "api", side_effect=[value, invalid]):
                with self.assertRaises(ValueError):
                    tap.release_hashes(VERSION)

    def test_api_auth_failure_is_not_treated_as_missing_branch(self):
        with patch.object(tap.subprocess, "run", return_value=
                subprocess.CompletedProcess([], 1, "", "gh: forbidden (HTTP 403)")):
            with self.assertRaises(RuntimeError):
                tap.api(tap.TAP, "git/ref/heads/example", missing_ok=True)

    def test_existing_branch_with_unrelated_edits_is_rejected(self):
        files = [{"filename": tap.FORMULA, "status": "modified"}, {"filename": "README.md", "status": "modified"}]
        with patch.object(tap, "api", return_value={"files": files}):
            with self.assertRaisesRegex(ValueError, "only Formula"):
                tap.validate_branch(SHA, HEAD, "expected")
        with patch.object(tap, "api", return_value={"files": files[:1]}), \
                patch.object(tap, "formula_at", return_value="different"):
            with self.assertRaisesRegex(ValueError, "will not be overwritten"):
                tap.validate_branch(SHA, HEAD, "expected")

    def test_closed_pr_is_not_reopened_or_duplicated(self):
        pr = copy.deepcopy(PR)
        pr["state"] = "closed"
        with patch.object(tap, "api", return_value=[pr]):
            with self.assertRaisesRegex(ValueError, "closed"):
                tap.find_pr(pr["head"]["ref"])

    def test_empty_or_incomplete_install_checks_are_not_success(self):
        for items in ([], checks()[:2]):
            with self.subTest(items=items), patch.object(tap, "api", return_value=PR), \
                    patch.object(tap, "command", return_value=subprocess.CompletedProcess([], 0, json.dumps(items), "")), \
                    patch.object(tap.time, "monotonic", side_effect=[0, 31]):
                with self.assertRaises(TimeoutError):
                    tap.wait_for_install(PR, HEAD, 30)

    def test_checks_not_yet_created_are_waited_for(self):
        results = [subprocess.CompletedProcess([], 1, "", "no checks reported on the branch"),
                   subprocess.CompletedProcess([], 0, json.dumps(checks()), "")]
        with patch.object(tap, "api", return_value=PR), patch.object(tap, "command", side_effect=results), \
                patch.object(tap.time, "sleep") as sleep:
            tap.wait_for_install(PR, HEAD, 30)
            sleep.assert_called_once()

    def test_additional_workflow_failure_and_mixed_run_results_are_rejected(self):
        failed = checks() + [{"name": "Update script tests", "workflow": "Install", "bucket": "fail", "link": "test"}]
        mixed = checks()
        mixed[-1]["link"] = mixed[-1]["link"].replace("/runs/123/", "/runs/456/")
        for items, error in ((failed, RuntimeError), (mixed, ValueError)):
            with self.subTest(items=items), patch.object(tap, "api", return_value=PR), \
                    patch.object(tap, "command", return_value=subprocess.CompletedProcess([], 0, json.dumps(items), "")):
                with self.assertRaises(error):
                    tap.wait_for_install(PR, HEAD, 30)

    def test_install_failure_skip_and_cancel_are_failures(self):
        for bucket in ("fail", "skipping", "cancel"):
            items = checks()
            items[-1]["bucket"] = bucket
            with self.subTest(bucket=bucket), patch.object(tap, "api", return_value=PR), \
                    patch.object(tap, "command", return_value=subprocess.CompletedProcess([], 1, json.dumps(items), "")):
                with self.assertRaisesRegex(RuntimeError, "Install did not pass"):
                    tap.wait_for_install(PR, HEAD, 30)

    def test_pr_head_changes_invalidate_results(self):
        changed = copy.deepcopy(PR)
        changed["head"]["sha"] = SHA
        with patch.object(tap, "api", return_value=changed), patch.object(tap, "command") as command:
            with self.assertRaisesRegex(ValueError, "PR changed"):
                tap.wait_for_install(PR, HEAD, 30)
            command.assert_not_called()

    def test_all_three_install_jobs_pass_without_merging(self):
        with patch.object(tap, "api", return_value=PR) as api, \
                patch.object(tap, "command", return_value=subprocess.CompletedProcess([], 0, json.dumps(checks()), "")) as cmd:
            tap.wait_for_install(PR, HEAD, 30)
            self.assertTrue(all("data" not in call.kwargs for call in api.call_args_list))
            self.assertEqual(cmd.call_args.args[:3], ("gh", "pr", "checks"))

    def test_dry_run_and_existing_pr_do_not_push_or_create_pr(self):
        for dry_run, existing in ((True, None), (False, PR)):
            def response(repo, path, **kwargs):
                self.assertNotIn("data", kwargs)
                if path == "git/ref/heads/main":
                    return {"object": {"sha": SHA}}
                return {"object": {"sha": HEAD}} if existing else None
            with self.subTest(dry_run=dry_run), \
                    patch.object(tap, "command", return_value=subprocess.CompletedProcess([], 0, f"https://github.com/{tap.TAP}.git\n", "")), \
                    patch.object(tap, "release_hashes", return_value=HASHES), \
                    patch.object(tap, "formula_at", return_value=FORMULA), \
                    patch.object(tap, "api", side_effect=response), \
                    patch.object(tap, "find_pr", return_value=existing), \
                    patch.object(tap, "validate_branch") as validate, \
                    patch.object(tap, "create_branch") as create, patch.object(tap, "wait_for_install") as wait:
                tap.run(self.args(dry_run=dry_run))
                create.assert_not_called()
                if dry_run:
                    wait.assert_not_called()
                else:
                    validate.assert_called_once()
                    wait.assert_called_once_with(PR, HEAD, 30)

    def test_already_updated_main_is_a_noop(self):
        formula = tap.update_formula(FORMULA, VERSION, HASHES)
        with patch.object(tap, "command", return_value=subprocess.CompletedProcess([], 0, f"https://github.com/{tap.TAP}.git\n", "")), \
                patch.object(tap, "release_hashes", return_value=HASHES), \
                patch.object(tap, "formula_at", return_value=formula), \
                patch.object(tap, "api", return_value={"object": {"sha": SHA}}), \
                patch.object(tap, "create_branch") as create, patch.object(tap, "find_pr") as find:
            tap.run(self.args())
            create.assert_not_called()
            find.assert_not_called()

    def test_branch_pushed_before_interruption_is_reused_to_create_pr(self):
        writes = []
        def response(repo, path, **kwargs):
            if "data" in kwargs:
                self.assertEqual((repo, path), (tap.TAP, "pulls"))
                writes.append(kwargs["data"])
                return PR
            return {"object": {"sha": SHA if path == "git/ref/heads/main" else HEAD}}
        with patch.object(tap, "command", return_value=subprocess.CompletedProcess([], 0, f"https://github.com/{tap.TAP}.git\n", "")), \
                patch.object(tap, "release_hashes", return_value=HASHES), \
                patch.object(tap, "formula_at", return_value=FORMULA), patch.object(tap, "api", side_effect=response), \
                patch.object(tap, "find_pr", return_value=None), patch.object(tap, "validate_branch") as validate, \
                patch.object(tap, "create_branch") as create, patch.object(tap, "wait_for_install") as wait:
            tap.run(self.args())
            create.assert_not_called()
            validate.assert_called_once()
            self.assertEqual(len(writes), 1)
            self.assertEqual((writes[0]["head"], writes[0]["base"]), ("chore/gitframe-1.2.3", "main"))
            wait.assert_called_once_with(PR, HEAD, 30)

    def test_temporary_checkout_creates_only_formula_commit_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original, remote = directory / "original", directory / "remote.git"
            identity = {"GIT_AUTHOR_NAME": "Release Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
                        "GIT_COMMITTER_NAME": "Release Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
            with patch.dict(os.environ, identity):
                def git(*args, cwd=directory):
                    return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.PIPE).strip()
                git("init", "--initial-branch=main", str(original))
                (original / "Formula").mkdir()
                (original / tap.FORMULA).write_text(FORMULA)
                git("add", ".", cwd=original)
                git("commit", "-m", "Initial Formula", cwd=original)
                base = git("rev-parse", "HEAD", cwd=original)
                git("clone", "--bare", str(original), str(remote))
                expected = tap.update_formula(FORMULA, VERSION, HASHES)
                real_command = tap.command
                def local_command(*args, **kwargs):
                    args = [str(remote) if value == f"https://github.com/{tap.TAP}.git" else value for value in args]
                    kwargs.setdefault("cwd", original)
                    return real_command(*args, **kwargs)
                with patch.object(tap, "command", side_effect=local_command):
                    head = tap.create_branch("chore/gitframe-1.2.3", base, expected, VERSION)
                self.assertEqual(git("rev-parse", "HEAD", cwd=original), base)
                self.assertEqual(git("status", "--porcelain", cwd=original), "")
                self.assertEqual(git("--git-dir", str(remote), "show", f"{head}:{tap.FORMULA}"), expected.strip())
                self.assertEqual(git("--git-dir", str(remote), "diff", "--name-only", base, head), tap.FORMULA)


if __name__ == "__main__":
    unittest.main()
