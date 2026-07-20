package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// viewConfigDashboard renders the unified configuration dashboard.
func (m Model) viewConfigDashboard() string {
	var b strings.Builder

	// Title
	b.WriteString(TitleStyle.Render("Download Configuration"))
	b.WriteString("\n\n")

	// Fields
	fields := []struct {
		f     dashField
		label string
		value string
	}{
		{dashMediaType, "Media Type", m.dashMediaTypeValue()},
		{dashQuality, "Quality", m.dashQualityValue()},
		{dashTrim, "Trim Video", m.dashTrimValue()},
		{dashTrimStart, "  Start Time", m.dashTrimStartValue()},
		{dashTrimEnd, "  End Time", m.dashTrimEndValue()},
		{dashSaveLocation, "Save Location", m.dashSaveLocationValue()},
	}

	for _, f := range fields {
		if !m.dashFieldVisible(f.f) {
			continue
		}

		selected := m.dashCursor == f.f

		// Render field row
		label := dashLabelStyle.Render(f.label)
		value := dashValueStyle.Render(f.value)

		var row string
		if selected {
			row = dashRowSelected.Render(fmt.Sprintf("%s  %s", label, value))
		} else {
			row = dashRowNormal.Render(fmt.Sprintf("%s  %s", label, value))
		}
		b.WriteString(row)
		b.WriteString("\n")

		// Show edit hint below the field when selected
		if selected && f.f != dashStartDownload && f.f != dashSaveLocation {
			var hint string
			switch f.f {
			case dashMediaType:
				hint = "  ← / →  switch between Audio / Video"
			case dashQuality:
				hint = "  ← / →  change quality preset"
			case dashTrim:
				hint = "  ← / →  toggle trim on / off"
			case dashTrimStart, dashTrimEnd:
				hint = "  Use --trim-start / --trim-end flags in CLI mode"
			}
			if hint != "" {
				b.WriteString(dashHintStyle.Render(hint))
				b.WriteString("\n")
			}
		}

		b.WriteString("\n")
	}

	// Start Download button row
	b.WriteString(m.dashStartDownloadRow())
	b.WriteString("\n")

	// Separator
	b.WriteString(Separator)
	b.WriteString("\n")

	// Help
	b.WriteString(dashHelpStyle.Render(
		"↑/↓ or Tab navigate  •  ←/→ change value  •  Enter open/confirm  •  Ctrl+C quit",
	))

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}

// ── Dashboard value formatters ───────────────────────────────

func (m Model) dashMediaTypeValue() string {
	if m.mediaType == MediaAudio {
		return "Audio"
	}
	return "Video"
}

func (m Model) dashQualityValue() string {
	if m.mediaType == MediaAudio {
		return "—"
	}
	return qualityPresets[m.qualityIdx]
}

func (m Model) dashTrimValue() string {
	if m.trimEnabled {
		return "Enabled"
	}
	return "Disabled"
}

func (m Model) dashTrimStartValue() string {
	if m.trimStart == "" {
		return "00:00:00"
	}
	return m.trimStart
}

func (m Model) dashTrimEndValue() string {
	if m.trimEnd == "" {
		return "00:00:00"
	}
	return m.trimEnd
}

func (m Model) dashSaveLocationValue() string {
	if m.outputDir == "" {
		return "~/Downloads"
	}
	return m.outputDir
}

func (m Model) dashStartDownloadRow() string {
	selected := m.dashCursor == dashStartDownload
	text := "[ Ctrl+D  or  Enter on \"Start Download\" to execute ]"

	if selected {
		return dashActionSelected.Render("  " + text)
	}
	return dashActionNormal.Render("  " + text)
}

// ── Dashboard styles ─────────────────────────────────────────

// ── Dir Picker (reused for overlay) ──────────────────────────

// viewDirPicker renders the directory picker with favorites + custom option.
func (m Model) viewDirPicker() string {
	var b strings.Builder

	b.WriteString(TitleStyle.Render("Choose output directory"))
	b.WriteString("\n\n")

	if m.dirShowCustom {
		b.WriteString(LabelStyle.Render("Enter custom path:"))
		b.WriteString("\n\n")
		b.WriteString(InputStyle.Render(m.dirInput.View()))
		b.WriteString("\n\n")
		b.WriteString(HelpStyle.Render("Enter to confirm  •  Esc to go back"))
	} else {
		for i, d := range m.dirFavorites {
			line := fmt.Sprintf("  %s", d.Label)
			if i == m.dirCursor {
				b.WriteString(cardSelected.Render("> "+line) + "\n")
			} else {
				b.WriteString(cardNormal.Render("  "+line) + "\n")
			}
		}

		b.WriteString("\n")
		b.WriteString(LabelStyle.Render("Current:"))
		b.WriteString(" ")
		b.WriteString(ValueStyle.Render(m.outputDir))
	}

	b.WriteString("\n")
	b.WriteString(Separator)
	b.WriteString("\n")
	b.WriteString(HelpStyle.Render("↑/↓ browse  •  Enter select  •  Esc go back  •  Ctrl+C quit"))

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}

var (
	dashLabelStyle = lipgloss.NewStyle().
			Width(16).
			Foreground(dimText)

	dashValueStyle = lipgloss.NewStyle().
			Foreground(text)

	dashRowBase = lipgloss.NewStyle().
			Padding(0, 2)

	dashRowSelected = dashRowBase.
			Background(bgLight).
			Foreground(accent).
			Bold(true)

	dashRowNormal = dashRowBase.
			Foreground(text)

	dashHintStyle = lipgloss.NewStyle().
			Foreground(dimText).
			PaddingLeft(4).
			Italic(true)

	dashHelpStyle = lipgloss.NewStyle().
			Foreground(dimText).
			Italic(true).
			MarginTop(1)

	dashActionBase = lipgloss.NewStyle().
			Padding(0, 2)

	dashActionSelected = dashActionBase.
				Background(success).
				Foreground(lipgloss.Color("#000000")).
				Bold(true)

	dashActionNormal = dashActionBase.
				Foreground(dimText)
)
