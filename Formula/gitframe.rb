class Gitframe < Formula
  desc "Terminal workspace for reviewing Git changes, source, and history"
  homepage "https://github.com/hiroaqii/gitframe"
  version "0.1.11"
  license "MIT"

  on_macos do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-macos-arm64.tar.gz"
    sha256 "5949c4e10547c67ee0cff10fb69a5d5d57e6fc1a30e485820bebb4f79747060e"

    depends_on arch: :arm64
    depends_on macos: :sequoia
  end

  on_linux do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-linux-x86_64.tar.gz"
    sha256 "08cedc9c497cff762c29e74f314933d8c4a2951d55bc789c6882023c346bea83"

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
