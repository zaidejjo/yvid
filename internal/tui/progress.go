package tui

import (
	"fmt"
	"path/filepath"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/zaidejjo/yvid/internal/ytdlp"
)

// viewProgress renders the download progress screen.
func (m Model) viewProgress() string {
	if m.loading {
		return m.viewLoading(m.loadingMsg)
	}

	var b strings.Builder

	b.WriteString(TitleStyle.Render("Downloading"))
	b.WriteString("\n\n")

	// Filename
	if m.progress.Filename != "" {
		b.WriteString(LabelStyle.Render("File:"))
		b.WriteString(" ")
		b.WriteString(ValueStyle.Render(pathBase(m.progress.Filename)))
		b.WriteString("\n\n")
	}

	// Progress bar — always render, even at 0%
	bar := m.progModel.ViewAs(m.progressBar)
	b.WriteString(bar)
	b.WriteString("\n")

	// Stats row — show dashes when unknown
	percent := fmt.Sprintf("%.1f%%", m.progress.Percent)
	speed := m.progress.Speed
	if speed == "" {
		speed = "---"
	}
	eta := m.progress.ETA
	if eta == "" {
		eta = "---"
	}
	downloaded := m.progress.Downloaded
	if downloaded == "" {
		downloaded = "---"
	}
	total := m.progress.Total
	if total == "" {
		total = "---"
	}

	b.WriteString(fmt.Sprintf("\n  %s  %s/s  ETA: %s  %s / %s\n",
		ProgressPercentStyle.Render(percent),
		speed, eta, downloaded, total,
	))

	b.WriteString("\n")
	b.WriteString(HelpStyle.Render("Downloading  •  Ctrl+C to cancel"))

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}

// viewComplete renders a premium success summary after download finishes.
func (m Model) viewComplete() string {
	var b strings.Builder

	// ── Top border banner ──
	banner := strings.Repeat("━", 50)
	b.WriteString(completeBannerStyle.Render(banner))
	b.WriteString("\n")

	checkRow := completeCheckStyle.Render("  ✓  Download Complete  ")
	b.WriteString(checkRow)
	b.WriteString("\n")

	b.WriteString(completeBannerStyle.Render(banner))
	b.WriteString("\n\n")

	// ── Summary card ──
	var card strings.Builder

	// File name
	filename := m.progress.Filename
	if filename == "" {
		filename = m.finalPath
	}
	if filename != "" {
		card.WriteString(fmt.Sprintf("  %s  %s\n",
			completeIconStyle.Render("📄"),
			completeLabelStyle.Render("File Name:"),
		))
		card.WriteString(fmt.Sprintf("     %s\n", completeValueStyle.Render(pathBase(filename))))
		card.WriteString("\n")
	}

	// Destination
	dest := m.finalPath
	if dest == "" {
		dest = m.outputDir
	}
	if dest != "" {
		absDest := dest
		if !filepath.IsAbs(absDest) {
			absDest, _ = filepath.Abs(absDest)
		}
		card.WriteString(fmt.Sprintf("  %s  %s\n",
			completeIconStyle.Render("📂"),
			completeLabelStyle.Render("Destination:"),
		))
		card.WriteString(fmt.Sprintf("     %s\n", completeValueStyle.Render(absDest)))
		card.WriteString("\n")
	}

	// Speed & time
	speed := m.finalSpeed
	if speed == "" || speed == "---" {
		speed = m.progress.Speed
	}
	if speed == "" || speed == "---" {
		speed = "N/A"
	}
	duration := m.finalDuration
	if duration == "" {
		duration = "N/A"
	}
	card.WriteString(fmt.Sprintf("  %s  %s\n",
		completeIconStyle.Render("⚡"),
		completeLabelStyle.Render("Speed & Time:"),
	))
	card.WriteString(fmt.Sprintf("     %s  •  %s\n",
		completeValueStyle.Render(speed+"/s"),
		completeSubLabelStyle.Render(duration),
	))

	// Render the card with a border
	cardStr := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(completeBorderColor).
		Padding(1, 1).
		Width(46).
		Render(card.String())
	b.WriteString(cardStr)
	b.WriteString("\n\n")

	// ── Action hint ──
	b.WriteString(completeActionStyle.Render(
		"[ Enter: New Download  •  O: Open Folder  •  Ctrl+C: Quit ]",
	))

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}

// ── Complete screen styles ──────────────────────────────────

var (
	completeBorderColor = lipgloss.Color("#34C759")

	completeBannerStyle = lipgloss.NewStyle().
				Foreground(completeBorderColor).
				Bold(true)

	completeCheckStyle = lipgloss.NewStyle().
				Foreground(lipgloss.Color("#FFFFFF")).
				Background(completeBorderColor).
				Bold(true).
				Padding(0, 1)

	completeIconStyle = lipgloss.NewStyle().
				Foreground(lipgloss.Color("#FFD700"))

	completeLabelStyle = lipgloss.NewStyle().
				Foreground(dimText)

	completeSubLabelStyle = lipgloss.NewStyle().
				Foreground(dimText).
				Italic(true)

	completeValueStyle = lipgloss.NewStyle().
				Foreground(text).
				Bold(true)

	completeActionStyle = lipgloss.NewStyle().
				Foreground(dimText).
				Italic(true).
				MarginTop(1)
)

// viewError renders the error screen.
func (m Model) viewError() string {
	var b strings.Builder

	b.WriteString(ErrorStyle.Render("✘ Error"))
	b.WriteString("\n\n")

	if m.err != nil {
		errorBlock := lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(errColor).
			Padding(0, 2).
			Render(m.err.Error())
		b.WriteString(errorBlock)
		b.WriteString("\n")
	}

	// Show cookie setup help when YouTube bot detection is hit
	if m.err != nil && ytdlp.IsBotError(m.err) {
		b.WriteString("\n")
		b.WriteString(WarningStyle.Render("! YouTube requires authentication"))
		b.WriteString("\n\n")
		b.WriteString(ValueStyle.Render("Quick fix — press a key to try a browser:"))
		b.WriteString("\n\n")
		b.WriteString(HelpStyle.Render("  C  Chrome  •  B  Brave  •  F  Firefox"))
		b.WriteString("\n")
		b.WriteString(HelpStyle.Render("  R  retry without cookies  •  Ctrl+C quit"))
	} else {
		b.WriteString("\n")
		b.WriteString(HelpStyle.Render("Press R to retry  •  Ctrl+C to quit"))
	}

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}

// pathBase returns the last component of a path (replaces filepath.Base to avoid import conflict).
func pathBase(path string) string {
	if idx := strings.LastIndexAny(path, "/\\"); idx >= 0 {
		return path[idx+1:]
	}
	return path
}
