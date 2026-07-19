package tui

import (
	"fmt"

	"github.com/charmbracelet/lipgloss"
	"github.com/zaidejjo/yvid/internal/ytdlp"
)

// viewFormatPicker renders the format/quality selection screen.
func (m Model) viewFormatPicker() string {
	b := lipgloss.NewStyle().Padding(1, 2)

	// Title
	content := TitleStyle.Render("Select format and quality") + "\n\n"

	// Video info (when metadata is available)
	if m.meta != nil {
		content += LabelStyle.Render("Title:") + " "
		content += ValueStyle.Render(truncateStr(m.meta.Title, 60)) + "\n"
		content += LabelStyle.Render("Uploader:") + " "
		content += ValueStyle.Render(m.meta.Uploader) + "\n"
		content += LabelStyle.Render("Duration:") + " "
		content += ValueStyle.Render(ytdlp.DurationStr(m.meta.Duration)) + "\n"
		content += "\n"
	}

	// Format options
	for i, opt := range m.formatOptions {
		var icon string
		switch opt.Type {
		case "video":
			icon = "🎬"
		case "audio":
			icon = "🎵"
		default:
			icon = "📄"
		}

		line := fmt.Sprintf(" %s  %s", icon, opt.Label)

		if i == m.formatCursor {
			content += ResultSelectedStyle.Render("▸ "+line) + "\n"
		} else {
			content += ResultItemStyle.Render("  "+line) + "\n"
		}
	}

	content += "\n"

	// Subtitles toggle
	subsStatus := "off"
	if m.selectedSubs {
		subsStatus = "on"
	}
	content += fmt.Sprintf(" Subtitles: [%s]  (press s to toggle)\n", subsStatus)

	content += "\n" + Separator + "\n"
	content += HelpStyle.Render("↑/↓ navigate  •  Enter download  •  s toggle subs  •  Ctrl+C quit")

	return b.Render(content)
}

func truncateStr(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}
