package tui

import (
	"fmt"
	"strings"
)

// viewInput renders the URL/search input screen.
func (m Model) viewInput() string {
	var b strings.Builder

	// Title
	b.WriteString(TitleStyle.Render("YVid — Video Downloader"))
	b.WriteString("\n\n")

	// Mode label
	var modeLabel string
	if m.inputMode {
		modeLabel = LabelStyle.Render("URL:")
	} else {
		modeLabel = LabelStyle.Render("Search:")
	}
	b.WriteString(modeLabel)
	b.WriteString(" ")

	// Input field
	if m.input.Focused() {
		b.WriteString(FocusedInputStyle.Render(m.input.View()))
	} else {
		b.WriteString(InputStyle.Render(m.input.View()))
	}

	b.WriteString("\n\n")

	// Help
	b.WriteString(HelpStyle.Render("Enter URL or search query  •  Ctrl+C to quit"))

	return AppStyle.Render(b.String())
}

// viewResults renders the search results screen.
func (m Model) viewResults() string {
	if m.loading {
		return m.viewLoading("Searching...")
	}

	var b strings.Builder
	b.WriteString(TitleStyle.Render(fmt.Sprintf("Search results for \"%s\"", m.query)))
	b.WriteString("\n\n")

	for i, r := range m.searchResults {
		line := fmt.Sprintf(" %s  %s  %s  %s",
			r.Duration,
			r.Title,
			r.Uploader,
			r.URL,
		)

		if i == m.cursor {
			b.WriteString(ResultSelectedStyle.Render("▸ " + line))
		} else {
			b.WriteString(ResultItemStyle.Render("  " + line))
		}
		b.WriteString("\n")
	}

	b.WriteString("\n")
	b.WriteString(Separator)
	b.WriteString("\n")
	b.WriteString(HelpStyle.Render("↑/↓ navigate  •  Enter select  •  Ctrl+C quit"))

	return AppStyle.Render(b.String())
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
