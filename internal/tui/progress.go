package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// viewProgress renders the download progress screen.
func (m Model) viewProgress() string {
	if m.loading {
		return m.viewLoading(m.loadingMsg)
	}

	var b strings.Builder

	b.WriteString(TitleStyle.Render("Downloading..."))
	b.WriteString("\n\n")

	// Filename
	if m.progress.Filename != "" {
		b.WriteString(LabelStyle.Render("File:"))
		b.WriteString(" ")
		b.WriteString(ValueStyle.Render(m.progress.Filename))
		b.WriteString("\n\n")
	}

	// Progress bar
	bar := m.progModel.ViewAs(m.progressBar)
	b.WriteString(bar)
	b.WriteString("\n")

	// Stats row
	b.WriteString(fmt.Sprintf("\n  %s  %s/s  ETA: %s  %s / %s\n",
		ProgressPercentStyle.Render(fmt.Sprintf("%.1f%%", m.progress.Percent)),
		m.progress.Speed,
		m.progress.ETA,
		m.progress.Downloaded,
		m.progress.Total,
	))

	b.WriteString("\n")
	b.WriteString(HelpStyle.Render("Downloading... Ctrl+C to cancel"))

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}

// viewComplete renders the download complete screen.
func (m Model) viewComplete() string {
	var b strings.Builder

	b.WriteString(SuccessStyle.Render("✓ Download Complete"))
	b.WriteString("\n\n")

	if m.progress.Filename != "" {
		b.WriteString(LabelStyle.Render("Saved:"))
		b.WriteString(" ")
		b.WriteString(ValueStyle.Render(m.progress.Filename))
		b.WriteString("\n")
	}

	b.WriteString(fmt.Sprintf("\n  %s / %s  •  %s\n",
		m.progress.Downloaded,
		m.progress.Total,
		m.progress.Speed,
	))

	b.WriteString("\n")
	b.WriteString(HelpStyle.Render("Press Enter for new download  •  Ctrl+C to quit"))

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}

// viewError renders the error screen.
func (m Model) viewError() string {
	var b strings.Builder

	b.WriteString(ErrorStyle.Render("✘ Error"))
	b.WriteString("\n\n")

	if m.err != nil {
		b.WriteString(ValueStyle.Render(m.err.Error()))
		b.WriteString("\n")
	}

	b.WriteString("\n")
	b.WriteString(HelpStyle.Render("Press R to retry  •  Ctrl+C to quit"))

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}

// UpdateProgress updates the download progress from a yt-dlp event.
func (m *Model) UpdateProgress(percent float64, speed, eta, downloaded, total string) {
	m.progress = DownloadProgress{
		Percent:    percent,
		Speed:      speed,
		ETA:        eta,
		Downloaded: downloaded,
		Total:      total,
	}
}
