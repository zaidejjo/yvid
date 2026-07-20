package ytdlp

import (
	"os/exec"
	"runtime"
)

// Available checks if yt-dlp is installed and reachable in PATH.
func Available() bool {
	_, err := exec.LookPath("yt-dlp")
	return err == nil
}

// InstallHint returns platform-specific installation instructions for yt-dlp.
func InstallHint() string {
	switch runtime.GOOS {
	case "linux":
		return "Install yt-dlp:\n" +
			"  sudo curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp\n" +
			"  sudo chmod a+rx /usr/local/bin/yt-dlp\n\n" +
			"  Or via package manager:\n" +
			"    sudo apt install yt-dlp        (Debian/Ubuntu)\n" +
			"    sudo pacman -S yt-dlp          (Arch)\n" +
			"    sudo dnf install yt-dlp        (Fedora)"

	case "darwin":
		return "Install yt-dlp:\n" +
			"  brew install yt-dlp\n\n" +
			"  Or download from:\n" +
			"  https://github.com/yt-dlp/yt-dlp/releases"

	case "windows":
		return "Install yt-dlp:\n" +
			"  winget install yt-dlp\n\n" +
			"  Or download from:\n" +
			"  https://github.com/yt-dlp/yt-dlp/releases"

	default:
		return "Install yt-dlp from: https://github.com/yt-dlp/yt-dlp/releases"
	}
}
