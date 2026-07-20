// Package tui provides the interactive Bubble Tea terminal UI for yvid.
package tui

import (
	"context"
	"fmt"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/zaidejjo/yvid/internal/config"
	"github.com/zaidejjo/yvid/internal/download"
	"github.com/zaidejjo/yvid/internal/ffmpeg"
	"github.com/zaidejjo/yvid/internal/ytdlp"
)

// ── Message types ──────────────────────────────────────────────

// depCheckResultMsg is sent after checking for yt-dlp and ffmpeg.
type depCheckResultMsg struct {
	ytdlpOK   bool
	ffmpegOK  bool
	partFiles []download.PartFile
}

// metadataMsg is sent when video metadata is fetched.
type metadataMsg struct {
	meta *ytdlp.VideoMetadata
}

// searchResultsMsg is sent when search results are fetched.
type searchResultsMsg struct {
	results []ytdlp.SearchResultItem
}

// errMsg is sent when an operation fails.
type errMsg struct {
	err error
}

// progressMsg wraps a yt-dlp progress event for the TUI.
type progressMsg struct {
	ytdlp.ProgressEvent
}

// downloadStartedMsg signals that download has begun.
type downloadStartedMsg struct{}

// downloadCompleteMsg signals that download finished successfully.
type downloadCompleteMsg struct {
	outputPath string
}

// ── Command constructors ───────────────────────────────────────

// fetchMetadataCmd spawns yt-dlp --dump-json for a given URL.
func fetchMetadataCmd(ctx context.Context, url string, cookiesFile, cookiesFromBrowser string) tea.Cmd {
	return func() tea.Msg {
		dl := ytdlp.NewDownloader()
		dl.SetCookies(cookiesFile, cookiesFromBrowser)
		meta, err := dl.FetchMetadata(ctx, url)
		if err != nil {
			return errMsg{err}
		}
		return metadataMsg{meta}
	}
}

// searchCmd spawns yt-dlp ytsearch5: for a query.
func searchCmd(ctx context.Context, query string, cookiesFile, cookiesFromBrowser string) tea.Cmd {
	return func() tea.Msg {
		dl := ytdlp.NewDownloader()
		dl.SetCookies(cookiesFile, cookiesFromBrowser)
		results, err := dl.Search(ctx, query)
		if err != nil {
			return errMsg{err}
		}
		return searchResultsMsg{results}
	}
}

// startDownloadCmd spawns yt-dlp download and feeds progress events.
func startDownloadCmd(ctx context.Context, opts ytdlp.Options, progressCh chan<- ytdlp.ProgressEvent) tea.Cmd {
	return func() tea.Msg {
		// Inject config defaults when options are empty
		if cfg, err := config.Load(); err == nil {
			if opts.ArchivePath == "" && cfg.DownloadArchive {
				opts.ArchivePath = cfg.ArchivePath()
			}
			if opts.CookiesFile == "" && opts.CookiesFromBrowser == "" {
				opts.CookiesFile = cfg.CookiesFile
				opts.CookiesFromBrowser = cfg.CookiesFromBrowser
			}
		}

		dl := ytdlp.NewDownloader()
		ch, err := dl.Download(ctx, opts)
		if err != nil {
			return errMsg{err}
		}

		// Relay progress events to the provided channel
		go func() {
			defer close(progressCh)
			for evt := range ch {
				progressCh <- evt
				if evt.Status == "completed" || evt.Status == "error" {
					return
				}
			}
		}()

		return downloadStartedMsg{}
	}
}

// waitForProgressCmd polls the progress channel and sends messages.
func waitForProgressCmd(ch <-chan ytdlp.ProgressEvent) tea.Cmd {
	return func() tea.Msg {
		evt, ok := <-ch
		if !ok {
			return downloadCompleteMsg{}
		}
		if evt.Status == "completed" {
			return downloadCompleteMsg{outputPath: evt.OutputPath}
		}
		if evt.Status == "error" {
			return errMsg{fmt.Errorf(evt.Message)}
		}
		return progressMsg{evt}
	}
}

// ── Dependency check ──────────────────────────────────────────

// depCheckCmd checks if yt-dlp and ffmpeg are available and scans for .part files.
func depCheckCmd() tea.Cmd {
	return func() tea.Msg {
		ytdlpOK := ytdlp.Available()
		ffmpegOK := ffmpeg.Available()

		// Scan for part files in output directory
		var partFiles []download.PartFile
		if cfg, err := config.Load(); err == nil && cfg.OutputDir != "" {
			parts, _ := download.ScanPartFiles(cfg.OutputDir)
			partFiles = parts
		}

		return depCheckResultMsg{
			ytdlpOK:   ytdlpOK,
			ffmpegOK:  ffmpegOK,
			partFiles: partFiles,
		}
	}
}

// ── Run ────────────────────────────────────────────────────────

// Run starts the interactive TUI.
func Run(ctx context.Context, url string, cookiesFile, cookiesFromBrowser string) error {
	m := NewModel(ctx)

	// CLI flags take priority, then fall back to config
	if cookiesFile == "" && cookiesFromBrowser == "" {
		if cfg, err := config.Load(); err == nil {
			m.cookiesFile = cfg.CookiesFile
			m.cookiesFromBrowser = cfg.CookiesFromBrowser
		}
	} else {
		m.cookiesFile = cookiesFile
		m.cookiesFromBrowser = cookiesFromBrowser
	}

	if url != "" {
		m.input.SetValue(url)
		m.query = url
		m.loading = true
		m.loadingMsg = "Fetching video info..."
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

	return nil
}
