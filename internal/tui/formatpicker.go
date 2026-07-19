package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// viewFormatPicker renders the format/quality selection screen.
func (m Model) viewFormatPicker() string {
	var b strings.Builder

	b.WriteString(TitleStyle.Render("Select format and quality"))
	b.WriteString("\n\n")

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
			b.WriteString(ResultSelectedStyle.Render("▸ " + line))
		} else {
			b.WriteString(ResultItemStyle.Render("  " + line))
		}
		b.WriteString("\n")
	}

	b.WriteString("\n")

	// Subtitles toggle
	subsStatus := "off"
	if m.selectedSubs {
		subsStatus = "on"
	}
	b.WriteString(fmt.Sprintf(" Subtitles: [%s]  (press s to toggle)\n", subsStatus))

	b.WriteString("\n")
	b.WriteString(Separator)
	b.WriteString("\n")
	b.WriteString(HelpStyle.Render("↑/↓ navigate  •  Enter download  •  s toggle subs  •  Ctrl+C quit"))

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}
