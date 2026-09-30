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

After publishing a GitFrame release, update the version and both SHA-256 hashes
in `Formula/gitframe.rb` using that release's `SHA256SUMS`. The download URLs
use the Formula version automatically. Submit the change and check the Install
workflow before merging it. The workflow downloads the published binaries on
Linux, macOS 15, and macOS 26 and tests both Homebrew and mise installation. On macOS it also
checks that the installed binary has no `com.apple.quarantine` attribute before
executing it. It never removes that attribute.
