class Gitframe < Formula
  desc "Terminal workspace for reviewing Git changes, source, and history"
  homepage "https://github.com/hiroaqii/gitframe"
  version "0.1.5"
  license "MIT"

  on_macos do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-macos-arm64.tar.gz"
    sha256 "13d4309fff10e66e95437843f63443e851b2bd70b00940b853159505fbabc1f5"

    depends_on arch: :arm64
    depends_on macos: :sequoia
  end

  on_linux do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-linux-x86_64.tar.gz"
    sha256 "114de48fdccaf7af44ec6eaad529dc93d3b21ee2d74d1b29f1ce7b342319eb60"

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
