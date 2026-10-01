class Gitframe < Formula
  desc "Terminal workspace for reviewing Git changes, source, and history"
  homepage "https://github.com/hiroaqii/gitframe"
  version "0.1.1"
  license "MIT"

  on_macos do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-macos-arm64.tar.gz"
    sha256 "2e0b467c973335cb2fa971cb5d2c414c70a6f87145406cb7c23a28f41319fdd0"

    depends_on arch: :arm64
    depends_on macos: :sequoia
  end

  on_linux do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-linux-x86_64.tar.gz"
    sha256 "42cc7b300ea69b33d1245a7a24ce10a8f5d7ac1d4c7025a8a58b2791032e4138"

    depends_on arch: :x86_64
  end

  depends_on "git"

  def install
    bin.install "gitframe"
  end

  test do
    if OS.mac?
      attributes = shell_output("/usr/bin/xattr #{bin}/gitframe").lines.map(&:strip)
      refute_includes attributes, "com.apple.quarantine"
    end
    assert_equal "gitframe #{version}", shell_output("#{bin}/gitframe --version").strip
    assert_match "--version", shell_output("#{bin}/gitframe --help")
  end
end
