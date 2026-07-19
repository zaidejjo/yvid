package tui

import (
	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
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
	// Screen management
	screen Screen

	// Input screen
	input     textinput.Model
	inputMode bool // true = paste URL, false = search query
	query     string

	// Search results (from yt-dlp --dump-json)
	searchResults []SearchResult
	cursor        int

	// Format picker
	formatOptions   []FormatOption
	formatCursor    int
	selectedFormat  string
	selectedQuality string
	selectedSubs    bool

	// Download progress
	progress   DownloadProgress
	downloaded bool

	// Error
	err error

	// Spinner for loading states
	spin       spinner.Model
	loading    bool
	loadingMsg string

	// Window size
	width  int
	height int

	// Done channel
	done bool
}

// SearchResult represents a video from yt-dlp search.
type SearchResult struct {
	Title    string
	URL      string
	Duration string
	Uploader string
	Views    int
}

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

// NewModel creates the initial TUI model.
func NewModel() Model {
	ti := textinput.New()
	ti.Placeholder = "Paste video URL or type search query..."
	ti.Focus()
	ti.CharLimit = 200
	ti.Width = 60

	s := spinner.New()
	s.Style = SpinnerStyle
	s.Spinner = spinner.Dot

	return Model{
		screen: ScreenInput,
		input:  ti,
		spin:   s,
	}
}

// Init initializes the Bubble Tea program.
func (m Model) Init() tea.Cmd {
	return tea.Batch(textinput.Blink, m.spin.Tick)
}

// Update handles events and user input.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		return m, nil

	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "q":
			return m, tea.Quit

		case "enter":
			switch m.screen {
			case ScreenInput:
				query := m.input.Value()
				if query == "" {
					return m, nil
				}
				m.query = query
				m.detectInputMode()
				m.loading = true
				return m, m.searchOrStart(query)

			case ScreenResults:
				if m.cursor < len(m.searchResults) {
					m.screen = ScreenFormat
				}
				return m, nil

			case ScreenFormat:
				m.selectedFormat = m.formatOptions[m.formatCursor].Value
				m.selectedQuality = m.formatOptions[m.formatCursor].Quality
				m.screen = ScreenProgress
				m.loading = true
				m.loadingMsg = "Starting download..."
				return m, m.startDownload()
			}

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
		}
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

// detectInputMode checks if input is a URL or search query.
func (m *Model) detectInputMode() {
	m.inputMode = false // simplified: always treat as potential URL for now
	// Full URL detection: regex for http/https
}

// searchOrStart handles URL vs search query.
func (m *Model) searchOrStart(query string) tea.Cmd {
	return func() tea.Msg {
		// TODO: spawn yt-dlp --dump-json or ytsearch:
		// For now, simulate
		if len(query) > 10 {
			m.screen = ScreenFormat
			m.formatOptions = defaultFormatOptions()
			return nil
		}
		// Simulate search results
		m.screen = ScreenResults
		m.searchResults = []SearchResult{
			{Title: "Example Video 1", URL: "https://youtube.com/watch?v=1", Duration: "3:30", Uploader: "Channel A"},
			{Title: "Example Video 2", URL: "https://youtube.com/watch?v=2", Duration: "5:45", Uploader: "Channel B"},
		}
		m.loading = false
		return nil
	}
}

// startDownload begins the download.
func (m *Model) startDownload() tea.Cmd {
	return func() tea.Msg {
		m.loading = false
		m.progress = DownloadProgress{
			Percent:    0,
			Speed:      "0 B/s",
			ETA:        "--:--",
			Downloaded: "0 B",
			Total:      "--",
		}
		return nil
	}
}

// defaultFormatOptions returns common format/quality options.
func defaultFormatOptions() []FormatOption {
	return []FormatOption{
		{Label: "Video (MP4) — Best Quality", Value: "mp4", Quality: "best", Type: "video"},
		{Label: "Video (MP4) — 2160p (4K)", Value: "mp4", Quality: "2160p", Type: "video"},
		{Label: "Video (MP4) — 1080p (Full HD)", Value: "mp4", Quality: "1080p", Type: "video"},
		{Label: "Video (MP4) — 720p (HD)", Value: "mp4", Quality: "720p", Type: "video"},
		{Label: "Video (MP4) — 480p (SD)", Value: "mp4", Quality: "480p", Type: "video"},
		{Label: "Audio (MP3) — Best Quality", Value: "mp3", Quality: "best", Type: "audio"},
	}
}

// ensure Model satisfies tea.Model
var _ tea.Model = Model{}
