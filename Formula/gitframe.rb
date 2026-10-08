class Gitframe < Formula
  desc "Terminal workspace for reviewing Git changes, source, and history"
  homepage "https://github.com/hiroaqii/gitframe"
  version "0.1.6"
  license "MIT"

  on_macos do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-macos-arm64.tar.gz"
    sha256 "934cd8e5d78ff263c55c21a38a996e732184672ad6c335684acb86702a463b26"

    depends_on arch: :arm64
    depends_on macos: :sequoia
  end

  on_linux do
    url "https://github.com/hiroaqii/gitframe/releases/download/v#{version}/gitframe-v#{version}-linux-x86_64.tar.gz"
    sha256 "2b1368d65d32be54304bfef2c3a41c190377e3b57a2248dc831d604704483f94"

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
