# Homebrew tap

[![Install](https://github.com/hiroaqii/homebrew-tap/actions/workflows/install.yml/badge.svg)](https://github.com/hiroaqii/homebrew-tap/actions/workflows/install.yml)

Install [GitFrame](https://github.com/hiroaqii/gitframe) from its GitHub Release
binaries. No Zig compiler is needed.

```sh
brew install hiroaqii/tap/gitframe
gitframe --version
```

Supported platforms:

- macOS 15 or newer on Apple Silicon, using native ARM Homebrew.
- Linux x86_64 with kernel 5.15 or newer and glibc 2.35 or newer.

Git is installed as a dependency. This tap uses a Formula for the command-line
executable.

To update:

```sh
brew update
brew upgrade hiroaqii/tap/gitframe
```

## Maintaining this tap

After publishing a GitFrame release, run the update script from this checkout.
It requires Python 3.10 or newer, Git, Ruby (for `ruby -c`), and GitHub CLI
authenticated with `gh auth login`. The account needs permission to push branches
and create PRs in `hiroaqii/homebrew-tap`; Git must have a commit name and email
configured. The script uses HTTPS with the GitHub CLI credential helper without
changing global Git configuration.

```sh
# Replace MAJOR.MINOR.PATCH with the published version, without a v prefix.
python3 scripts/update-gitframe.py MAJOR.MINOR.PATCH --dry-run
python3 scripts/update-gitframe.py MAJOR.MINOR.PATCH
```

The dry run validates the published release, checksums, and Formula syntax, and
shows the proposed diff. It does not create a branch, commit, or PR.

The normal command updates the version and both SHA-256 hashes using the
published `SHA256SUMS`, verified against GitHub's asset digests. It creates
`chore/gitframe-MAJOR.MINOR.PATCH` in a temporary checkout of the remote `main`,
commits and pushes only the Formula change, opens a PR, and waits for the three
Install jobs. Your local checkout, branch, and uncommitted files remain unchanged.
The script does not merge: review and merge the PR after the checks pass to make
the new version available through Homebrew.

Rerun the same command after interruption to reuse the branch and PR. If `main`
already contains that version and the same hashes, it exits without changes.
An existing branch with unexpected edits, a closed PR without the expected
Formula on `main`, mismatched hashes, or an attempted downgrade stops the command.
Existing branches are never force-pushed. If Install fails, rerun its failed jobs
in Actions, then rerun this script to wait for the result. `--timeout SECONDS`
changes the 30-minute wait limit; Ctrl-C or a timeout leaves the PR and Actions
available for resumption.

You can also update `Formula/gitframe.rb` manually using the release's
`SHA256SUMS`; its download URLs use the Formula version automatically. Submit a
PR and check the Install workflow before merging. It downloads published binaries on
Linux, macOS 15, and macOS 26 and tests both Homebrew and mise installation. On macOS it also
checks that the installed binary has no `com.apple.quarantine` attribute before
executing it. It never removes that attribute.

Run the automation tests locally without publishing anything:

```sh
python3 -m unittest discover -s scripts -p '*_test.py' -v
```
