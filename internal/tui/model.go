package tui

import (
	"context"
	"fmt"
	"regexp"
	"strings"

	"github.com/charmbracelet/bubbles/progress"
	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/zaidejjo/yvid/internal/ytdlp"
)

// Screen represents the current TUI screen.
type Screen int

const (
	ScreenInput    Screen = iota // URL/search input
	ScreenResults                // Search results
	ScreenFormat                 // Format/quality picker
	ScreenProgress               // Download progress
	ScreenComplete               // Download complete
	ScreenError                  // Error display
)

// Model is the main Bubble Tea model for yvid.
type Model struct {
	// Context for cancellation
	ctx context.Context

	// Screen management
	screen Screen

	// Input screen
	input     textinput.Model
	inputMode InputMode
	query     string

	// Search results (from yt-dlp --dump-json)
	searchResults []ytdlp.SearchResultItem
	cursor        int

	// Single video metadata (for URL input)
	meta *ytdlp.VideoMetadata

	// Format picker
	formatOptions  []FormatOption
	formatCursor   int
	selectedFormat string
	selectedQual   string
	selectedSubs   bool

	// Download progress
	progModel    progress.Model
	progress     DownloadProgress
	progressCh   chan ytdlp.ProgressEvent
	progressBar  float64
	downloadDone bool
	finalPath    string

	// Error
	err error

	// Spinner for loading states
	spin       spinner.Model
	loading    bool
	loadingMsg string

	// Window size
	width  int
	height int

	// done flag
	done bool
}

// InputMode indicates whether input is a URL or search query.
type InputMode int

const (
	InputAuto InputMode = iota
	InputURL
	InputSearch
)

// FormatOption represents a downloadable format.
type FormatOption struct {
	Label   string
	Value   string
	Quality string
	Type    string // "video", "audio"
}

// DownloadProgress tracks the current download.
type DownloadProgress struct {
	Percent    float64
	Speed      string
	ETA        string
	Downloaded string
	Total      string
	Filename   string
}

// urlRegex matches http/https URLs.
var urlRegex = regexp.MustCompile(`^https?://`)

// NewModel creates the initial TUI model.
func NewModel(ctx context.Context) Model {
	ti := textinput.New()
	ti.Placeholder = "Paste video URL or type search query..."
	ti.Focus()
	ti.CharLimit = 200
	ti.Width = 60

	s := spinner.New()
	s.Style = SpinnerStyle
	s.Spinner = spinner.Dot

	p := progress.New(
		progress.WithDefaultGradient(),
		progress.WithWidth(50),
	)

	return Model{
		ctx:        ctx,
		screen:     ScreenInput,
		input:      ti,
		spin:       s,
		progModel:  p,
		progressCh: make(chan ytdlp.ProgressEvent, 64),
	}
}

// Init initializes the Bubble Tea program.
func (m Model) Init() tea.Cmd {
	cmds := []tea.Cmd{textinput.Blink, m.spin.Tick}

	// If URL pre-filled on startup, auto-fetch
	if m.query != "" {
		cmds = append(cmds, m.startMetadataFetch(m.query))
	}

	return tea.Batch(cmds...)
}

// Update handles events and user input.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		return m, nil

	case tea.KeyMsg:
		return m.handleKeyMsg(msg)

	case metadataMsg:
		m.loading = false
		m.meta = msg.meta
		m.screen = ScreenFormat
		m.formatOptions = buildFormatOptions(msg.meta)
		return m, nil

	case searchResultsMsg:
		m.loading = false
		m.searchResults = msg.results
		m.cursor = 0
		m.screen = ScreenResults
		return m, nil

	case errMsg:
		m.loading = false
		m.err = msg.err
		m.screen = ScreenError
		return m, nil

	case downloadStartedMsg:
		m.loading = false
		// Start polling progress channel
		return m, waitForProgressCmd(m.progressCh)

	case progressMsg:
		m.updateProgressFromEvent(msg.ProgressEvent)
		// Keep polling
		return m, waitForProgressCmd(m.progressCh)

	case downloadCompleteMsg:
		m.downloadDone = true
		m.finalPath = msg.outputPath
		m.screen = ScreenComplete
		return m, nil
	}

	// Handle text input
	if m.screen == ScreenInput {
		var cmd tea.Cmd
		m.input, cmd = m.input.Update(msg)
		return m, cmd
	}

	// Handle spinner
	var cmd tea.Cmd
	m.spin, cmd = m.spin.Update(msg)
	return m, cmd
}

// ── Key handling ───────────────────────────────────────────────

func (m Model) handleKeyMsg(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "ctrl+c", "q":
		return m, tea.Quit

	case "enter":
		return m.handleEnter()

	case "up", "k":
		switch m.screen {
		case ScreenResults:
			if m.cursor > 0 {
				m.cursor--
			}
		case ScreenFormat:
			if m.formatCursor > 0 {
				m.formatCursor--
			}
		}

	case "down", "j":
		switch m.screen {
		case ScreenResults:
			if m.cursor < len(m.searchResults)-1 {
				m.cursor++
			}
		case ScreenFormat:
			if m.formatCursor < len(m.formatOptions)-1 {
				m.formatCursor++
			}
		}

	case "s":
		if m.screen == ScreenFormat {
			m.selectedSubs = !m.selectedSubs
		}

	case "r":
		if m.screen == ScreenError || m.screen == ScreenComplete {
			m.err = nil
			m.screen = ScreenInput
			m.input.Focus()
			m.input.SetValue("")
		}
	}

	return m, nil
}

func (m Model) handleEnter() (tea.Model, tea.Cmd) {
	switch m.screen {
	case ScreenInput:
		query := strings.TrimSpace(m.input.Value())
		if query == "" {
			return m, nil
		}
		m.query = query
		m.detectInputMode()
		m.loading = true
		return m, m.startMetadataFetch(query)

	case ScreenResults:
		if m.cursor < len(m.searchResults) {
			// Selected a search result — fetch its full metadata
			selected := m.searchResults[m.cursor]
			m.loading = true
			m.loadingMsg = "Fetching video info..."
			return m, fetchMetadataCmd(m.ctx, selected.URL)
		}

	case ScreenFormat:
		if m.formatCursor < len(m.formatOptions) {
			opt := m.formatOptions[m.formatCursor]
			m.selectedFormat = opt.Value
			m.selectedQual = opt.Quality
			m.screen = ScreenProgress
			m.loading = true
			m.loadingMsg = "Starting download..."
			return m, m.startDownload()
		}

	case ScreenComplete:
		m.screen = ScreenInput
		m.input.Focus()
		m.input.SetValue("")
	}

	return m, nil
}

// ── Input detection ────────────────────────────────────────────

func (m *Model) detectInputMode() {
	if urlRegex.MatchString(m.query) {
		m.inputMode = InputURL
	} else {
		m.inputMode = InputSearch
	}
	m.loadingMsg = "Fetching video info..."
	if m.inputMode == InputSearch {
		m.loadingMsg = "Searching..."
	}
}

// startMetadataFetch returns a tea.Cmd that fetches metadata or search results.
func (m *Model) startMetadataFetch(query string) tea.Cmd {
	if urlRegex.MatchString(query) {
		return fetchMetadataCmd(m.ctx, query)
	}
	return searchCmd(m.ctx, query)
}

// ── Format options ─────────────────────────────────────────────

func buildFormatOptions(meta *ytdlp.VideoMetadata) []FormatOption {
	opts := []FormatOption{
		{Label: "Video (MP4) — Best", Value: "mp4", Quality: "best", Type: "video"},
		{Label: "Video (MP4) — 2160p (4K)", Value: "mp4", Quality: "2160p", Type: "video"},
		{Label: "Video (MP4) — 1080p (Full HD)", Value: "mp4", Quality: "1080p", Type: "video"},
		{Label: "Video (MP4) — 720p (HD)", Value: "mp4", Quality: "720p", Type: "video"},
		{Label: "Video (MP4) — 480p (SD)", Value: "mp4", Quality: "480p", Type: "video"},
		{Label: "Audio (MP3) — Best", Value: "mp3", Quality: "best", Type: "audio"},
	}

	// If metadata has format info, add detected resolutions
	seen := map[string]bool{}
	for _, f := range meta.Formats {
		if f.Height > 0 && f.Ext == "mp4" {
			label := fmt.Sprintf("%dp", f.Height)
			if !seen[label] {
				seen[label] = true
				opts = append(opts, FormatOption{
					Label:   fmt.Sprintf("Video (MP4) — %s (%s)", label, f.FormatNote),
					Value:   "mp4",
					Quality: label,
					Type:    "video",
				})
			}
		}
	}

	return opts
}

// ── Download ───────────────────────────────────────────────────

func (m *Model) startDownload() tea.Cmd {
	// Determine URL
	targetURL := m.query
	if m.meta != nil {
		targetURL = m.meta.URL
	} else if len(m.searchResults) > 0 && m.cursor < len(m.searchResults) {
		targetURL = m.searchResults[m.cursor].URL
	}

	opts := ytdlp.Options{
		URL:       targetURL,
		Format:    m.selectedFormat,
		Quality:   m.selectedQual,
		Subtitles: m.selectedSubs,
	}

	return startDownloadCmd(m.ctx, opts, m.progressCh)
}

func (m *Model) updateProgressFromEvent(evt ytdlp.ProgressEvent) {
	m.progress = DownloadProgress{
		Percent:    evt.Percent,
		Speed:      evt.SpeedHuman(),
		ETA:        evt.ETAHuman(),
		Downloaded: formatBytes(evt.Downloaded),
		Total:      formatBytes(evt.Total),
	}
	if evt.OutputPath != "" {
		m.progress.Filename = evt.OutputPath
	}
	m.progressBar = evt.Percent / 100.0
}

func formatBytes(b int64) string {
	if b <= 0 {
		return "---"
	}
	switch {
	case b >= 1_000_000_000:
		return fmt.Sprintf("%.2f GB", float64(b)/1_000_000_000)
	case b >= 1_000_000:
		return fmt.Sprintf("%.2f MB", float64(b)/1_000_000)
	case b >= 1_000:
		return fmt.Sprintf("%.1f KB", float64(b)/1_000)
	default:
		return fmt.Sprintf("%d B", b)
	}
}

// View renders the current screen.
func (m Model) View() string {
	if m.done {
		return ""
	}

	switch m.screen {
	case ScreenInput:
		return m.viewInput()
	case ScreenResults:
		return m.viewResults()
	case ScreenFormat:
		return m.viewFormatPicker()
	case ScreenProgress:
		return m.viewProgress()
	case ScreenComplete:
		return m.viewComplete()
	case ScreenError:
		return m.viewError()
	default:
		return "yvid"
	}
}

// ensure Model satisfies tea.Model
var _ tea.Model = Model{}
