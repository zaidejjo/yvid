// Package notify provides cross-platform desktop notifications.
package notify

import (
	"fmt"
	"os/exec"
	"runtime"
)

// Notification represents a desktop notification.
type Notification struct {
	Title   string
	Message string
	Icon    string // path to icon file
}

// Send dispatches a desktop notification using the platform-native mechanism.
func Send(n Notification) error {
	switch runtime.GOOS {
	case "linux":
		return notifyLinux(n)
	case "darwin":
		return notifyMacOS(n)
	case "windows":
		return notifyWindows(n)
	default:
		return fmt.Errorf("unsupported platform: %s", runtime.GOOS)
	}
}

func notifyLinux(n Notification) error {
	args := []string{"--app-name", "YVid"}
	if n.Icon != "" {
		args = append(args, "--icon", n.Icon)
	}
	args = append(args, n.Title, n.Message)
	return exec.Command("notify-send", args...).Run()
}

func notifyMacOS(n Notification) error {
	script := fmt.Sprintf(
		`display notification "%s" with title "%s"`,
		n.Message, n.Title,
	)
	return exec.Command("osascript", "-e", script).Run()
}

func notifyWindows(n Notification) error {
	// PowerShell-based toast notification
	script := fmt.Sprintf(`
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName("text")
$textNodes.Item(0).AppendChild($template.CreateTextNode("%s")) > $null
$textNodes.Item(1).AppendChild($template.CreateTextNode("%s")) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("YVid").Show($toast)
`, n.Title, n.Message)
	return exec.Command("powershell", "-Command", script).Run()
}

// SendSimple sends a notification with just title and message.
func SendSimple(title, message string) error {
	return Send(Notification{Title: title, Message: message})
}

// SendDownloadComplete sends a notification for completed downloads.
func SendDownloadComplete(filename string) error {
	return SendSimple("YVid", fmt.Sprintf("Download complete: %s", filename))
}

// SendError sends a notification for download errors.
func SendError(message string) error {
	return SendSimple("YVid Error", message)
}
