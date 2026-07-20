package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/zaidejjo/yvid/internal/ytdlp"
)

// viewInput renders the URL/search input screen.
func (m Model) viewInput() string {
	if m.loading {
		return m.viewLoading(m.loadingMsg)
	}

	var b strings.Builder

	// Title
	b.WriteString(TitleStyle.Render("YVid — Video Downloader"))
	b.WriteString("\n\n")

	// Input field
	input := m.input.View()
	if m.input.Focused() {
		b.WriteString(FocusedInputStyle.Render(input))
	} else {
		b.WriteString(InputStyle.Render(input))
	}

	b.WriteString("\n\n")

	// Help
	b.WriteString(HelpStyle.Render("Paste URL or search query  •  Ctrl+C quit"))

	return AppStyle.Render(b.String())
}

// viewResults renders the search results screen.
func (m Model) viewResults() string {
	if m.loading {
		return m.viewLoading("Searching...")
	}

	var b strings.Builder
	b.WriteString(TitleStyle.Render(fmt.Sprintf("Search: \"%s\"", truncateStr(m.query, 40))))
	b.WriteString("\n\n")

	// Results as clean list
	for i, r := range m.searchResults {
		title := truncateStr(r.Title, 50)
		meta := fmt.Sprintf("%s  •  %s  •  %s",
			ytdlp.DurationStr(r.Duration),
			r.Uploader,
			formatCount(r.ViewCount),
		)

		itemStyle := lipgloss.NewStyle().Padding(0, 2)
		if i == m.cursor {
			itemStyle = itemStyle.Foreground(accent).Background(bgLight).Bold(true)
			b.WriteString(itemStyle.Render(fmt.Sprintf("> %s", title)) + "\n")
			b.WriteString(itemStyle.Copy().Foreground(dimText).Bold(false).Render(fmt.Sprintf("  %s", meta)) + "\n")
		} else {
			itemStyle = itemStyle.Foreground(text)
			b.WriteString(itemStyle.Render(fmt.Sprintf("  %s", title)) + "\n")
			b.WriteString(itemStyle.Copy().Foreground(dimText).Render(fmt.Sprintf("  %s", meta)) + "\n")
		}
		b.WriteString("\n")
	}

	b.WriteString(Separator)
	b.WriteString("\n")
	b.WriteString(HelpStyle.Render("↑/↓ navigate  •  Enter select  •  Ctrl+C quit"))

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}

// viewLoading renders a loading spinner with a message.
func (m Model) viewLoading(msg string) string {
	var b strings.Builder
	b.WriteString(TitleStyle.Render("YVid"))
	b.WriteString("\n\n")
	b.WriteString(SpinnerStyle.Render(m.spin.View()))
	b.WriteString(" ")
	b.WriteString(ValueStyle.Render(msg))
	return AppStyle.Render(b.String())
}

func formatCount(n int64) string {
	if n <= 0 {
		return ""
	}
	switch {
	case n >= 1_000_000:
		return fmt.Sprintf("%.1fM views", float64(n)/1_000_000)
	case n >= 1_000:
		return fmt.Sprintf("%.0fK views", float64(n)/1_000)
	default:
		return fmt.Sprintf("%d views", n)
	}
}
