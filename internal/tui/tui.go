// Package tui provides the interactive Bubble Tea terminal UI for yvid.
package tui

import (
	"context"
	"fmt"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/zaidejjo/yvid/internal/ytdlp"
)

// Run starts the interactive TUI for downloading a URL.
// If url is empty, starts at the input screen.
// If url is provided, starts at the format picker.
func Run(ctx context.Context, url string) error {
	m := NewModel()

	if url != "" {
		m.input.SetValue(url)
		m.query = url
		m.detectInputMode()
		// Will transition after tick
	}

	p := tea.NewProgram(m, tea.WithAltScreen())

	model, err := p.Run()
	if err != nil {
		return fmt.Errorf("TUI error: %w", err)
	}

	final := model.(Model)
	if final.err != nil {
		return final.err
	}

	// If a download was configured, launch it
	if final.selectedFormat != "" && final.query != "" {
		return startDownload(ctx, final)
	}

	return nil
}

// startDownload launches the yt-dlp subprocess and feeds progress to the TUI.
func startDownload(ctx context.Context, m Model) error {
	opts := ytdlp.Options{
		URL:       m.query,
		Format:    m.selectedFormat,
		Quality:   m.selectedQuality,
		Subtitles: m.selectedSubs,
	}

	dl := ytdlp.NewDownloader()
	progressCh, err := dl.Download(ctx, opts)
	if err != nil {
		return fmt.Errorf("download failed: %w", err)
	}

	// Create a progress-only TUI
	progModel := progressModel{
		ch: progressCh,
	}
	p := tea.NewProgram(progModel, tea.WithAltScreen())

	_, err = p.Run()
	return err
}

// progressModel is a simpler TUI for showing download progress.
type progressModel struct {
	ch      <-chan ytdlp.ProgressEvent
	percent float64
	speed   string
	eta     string
	done    bool
	err     error
}

func (m progressModel) Init() tea.Cmd {
	return nil
}

func (m progressModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		if msg.String() == "ctrl+c" {
			return m, tea.Quit
		}

	case ytdlp.ProgressEvent:
		switch msg.Status {
		case "downloading":
			m.percent = msg.Percent
			m.speed = msg.SpeedHuman()
			m.eta = msg.ETAHuman()
		case "completed":
			m.done = true
			return m, tea.Quit
		case "error":
			m.err = fmt.Errorf(msg.Message)
			return m, tea.Quit
		}
	}

	// Poll for progress
	select {
	case evt, ok := <-m.ch:
		if !ok {
			m.done = true
			return m, tea.Quit
		}
		return m, func() tea.Msg { return evt }
	default:
		return m, nil
	}
}

func (m progressModel) View() string {
	if m.err != nil {
		return fmt.Sprintf("✘ Error: %s\n", m.err)
	}
	if m.done {
		return "✓ Download complete!\n"
	}
	return fmt.Sprintf("Downloading... %.1f%%  %s/s  ETA: %s\n", m.percent, m.speed, m.eta)
}
