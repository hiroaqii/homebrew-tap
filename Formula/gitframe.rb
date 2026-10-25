class Gitframe < Formula
  desc "Terminal workspace for reviewing Git changes, source, and history"
  homepage "https://github.com/hiroaqii/gitframe"
  version "0.1.9"
  license "MIT"

  on_macos do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-macos-arm64.tar.gz"
    sha256 "a0513a534ed383575048e4e7ba53329b07da0e1414740c7adea2e32a8dbcf264"

    depends_on arch: :arm64
    depends_on macos: :sequoia
  end

  on_linux do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-linux-x86_64.tar.gz"
    sha256 "13d70ef56a0e0095e42e0d717d6fba0deafa5425b682d0608bf828eb507e3f21"

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
