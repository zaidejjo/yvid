package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/zaidejjo/yvid/internal/config"
	"github.com/zaidejjo/yvid/internal/download"
	"github.com/zaidejjo/yvid/internal/ffmpeg"
	"github.com/zaidejjo/yvid/internal/ytdlp"
)

// ── Dependency check view ──────────────────────────────────────

func (m Model) viewDepCheck() string {
	var b strings.Builder

	b.WriteString(TitleStyle.Render("yvid — Pre-flight Check"))
	b.WriteString("\n\n")

	// yt-dlp
	b.WriteString(m.depRow("yt-dlp", m.ytdlpAvailable))
	b.WriteString("\n")
	b.WriteString(m.depRow("ffmpeg", m.ffmpegAvailable))
	b.WriteString("\n\n")

	if !m.ytdlpAvailable {
		b.WriteString(ErrorStyle.Render("✘ yt-dlp is required"))
		b.WriteString("\n\n")
		b.WriteString(ValueStyle.Render(ytdlp.InstallHint()))
		b.WriteString("\n\n")
	}

	if !m.ffmpegAvailable {
		b.WriteString(WarningStyle.Render("! ffmpeg not found — trim unavailable"))
		b.WriteString("\n")
		b.WriteString(ValueStyle.Render(ffmpeg.InstallHint()))
		b.WriteString("\n\n")
	}

	// Part files
	if len(m.partFiles) > 0 {
		b.WriteString(WarningStyle.Render("! Incomplete downloads detected"))
		b.WriteString("\n\n")
		b.WriteString(ValueStyle.Render(download.PartFileInfo(m.partFiles)))
		b.WriteString("\n\n")
		b.WriteString(HelpStyle.Render("Run yvid with the same URL to resume automatically"))
		b.WriteString("\n\n")
	}

	if m.ytdlpAvailable {
		b.WriteString(HelpStyle.Render("Press Enter to continue  •  Ctrl+C to quit"))
	} else {
		b.WriteString(HelpStyle.Render("Install yt-dlp, then press R to recheck  •  Ctrl+C to quit"))
	}

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}

func (m Model) depRow(name string, ok bool) string {
	icon := SuccessStyle.Render("✓")
	if !ok {
		icon = ErrorStyle.Render("✘")
	}
	status := ValueStyle.Render(name)
	return fmt.Sprintf("  %s  %s", icon, status)
}

// ── Config check view ──────────────────────────────────────────

func (m Model) viewConfigCheck() string {
	var b strings.Builder

	b.WriteString(TitleStyle.Render("Configuration"))
	b.WriteString("\n\n")

	cfg, err := config.Load()
	if err != nil {
		b.WriteString(ErrorStyle.Render("Failed to load config: " + err.Error()))
	} else {
		b.WriteString(LabelStyle.Render("Config file:"))
		b.WriteString(" ")
		b.WriteString(ValueStyle.Render(cfg.Path()))
		b.WriteString("\n\n")

		lines := strings.Split(cfg.Render(), "\n")
		for _, line := range lines {
			if line != "" && !strings.HasPrefix(line, "#") {
				b.WriteString("  ")
				b.WriteString(ValueStyle.Render(line))
				b.WriteString("\n")
			}
		}

		// Archive status
		archivePath := cfg.ArchivePath()
		archive, err := download.NewArchive(archivePath)
		if err == nil {
			b.WriteString("\n")
			b.WriteString(LabelStyle.Render("Download archive:"))
			b.WriteString(" ")
			b.WriteString(ValueStyle.Render(archivePath))
			b.WriteString("\n")
			b.WriteString(fmt.Sprintf("  %d entries\n", archive.Count()))
		}
	}

	b.WriteString("\n")
	b.WriteString(HelpStyle.Render("Press Enter to continue  •  Ctrl+C to quit"))

	return lipgloss.NewStyle().Padding(1, 2).Render(b.String())
}
