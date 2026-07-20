package tui

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/progress"
	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/zaidejjo/yvid/internal/config"
	"github.com/zaidejjo/yvid/internal/download"
	"github.com/zaidejjo/yvid/internal/ytdlp"
)

// Screen represents the current TUI screen.
type Screen int

const (
	ScreenDepCheck         Screen = iota
	ScreenInput                   // URL/search input
	ScreenResults                 // Search results
	ScreenConfigDashboard         // Unified configuration dashboard
	ScreenDirPickerOverlay        // Directory picker overlay on dashboard
	ScreenProgress                // Download progress
	ScreenComplete                // Download complete
	ScreenError                   // Error display
)

// dashField identifies a configurable field on the dashboard.
type dashField int

const (
	dashMediaType dashField = iota
	dashQuality
	dashTrim
	dashTrimStart
	dashTrimEnd
	dashSaveLocation
	dashStartDownload
	dashFieldCount
)

// MediaType selection.
type MediaType int

const (
	MediaVideo MediaType = iota
	MediaAudio
)

var mediaTypeLabels = []string{"Video", "Audio"}

// Quality presets.
var qualityPresets = []string{"Best", "2160p (4K)", "1080p", "720p", "480p"}
var qualityValues = []string{"best", "2160p", "1080p", "720p", "480p"}

// DirItem represents a directory option in the picker.
type DirItem struct {
	Label    string
	Path     string
	IsCustom bool
}

// Model is the main Bubble Tea model for yvid.
type Model struct {
	// Context
	ctx context.Context

	// Screen
	screen Screen

	// Dep check
	depCheckDone    bool
	ytdlpAvailable  bool
	ffmpegAvailable bool
	partFiles       []download.PartFile

	// Input (URL / search)
	input     textinput.Model
	inputMode InputMode
	query     string

	// Search results
	searchResults []ytdlp.SearchResultItem
	cursor        int

	// Dashboard config values
	mediaType   MediaType // audio/video
	qualityIdx  int       // index into qualityPresets
	trimEnabled bool
	trimStart   string
	trimEnd     string
	outputDir   string // final chosen directory

	// Dashboard navigation
	dashCursor      dashField // which field is highlighted
	dirPickerActive bool      // dir picker overlay active

	// Dir picker overlay state
	dirInput      textinput.Model
	dirFavorites  []DirItem
	dirCursor     int
	dirShowCustom bool

	// Favorites from config
	favoriteDirs []DirItem

	// Metadata (fetched lazily before download)
	meta       *ytdlp.VideoMetadata
	formatOpts []ytdlp.Options // resolved options after metadata

	// Download
	progModel   progress.Model
	progress    DownloadProgress
	progressCh  chan ytdlp.ProgressEvent
	progressBar float64
	downloadOK  bool
	finalPath   string

	// Complete screen info
	finalSpeed    string
	finalDuration string
	downloadStart time.Time

	// Error
	err error

	// Loading
	spin       spinner.Model
	loading    bool
	loadingMsg string

	// Window
	width  int
	height int
	done   bool

	// Config-derived
	archivePath        string
	cookiesFile        string
	cookiesFromBrowser string
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

var urlRegex = regexp.MustCompile(`^https?://`)

// InputMode indicates whether input is a URL or search query.
type InputMode int

const (
	InputAuto InputMode = iota
	InputURL
	InputSearch
)

// ── Model lifecycle ──────────────────────────────────────────

func NewModel(ctx context.Context) Model {
	ti := textinput.New()
	ti.Placeholder = "Paste video URL or type search query..."
	ti.Focus()
	ti.CharLimit = 200
	ti.Width = 60

	di := textinput.New()
	di.Placeholder = "Type a custom path..."
	di.CharLimit = 300
	di.Width = 60

	s := spinner.New()
	s.Style = SpinnerStyle
	s.Spinner = spinner.Dot

	p := progress.New(
		progress.WithDefaultGradient(),
		progress.WithWidth(50),
	)

	// Load config
	cfg, _ := config.Load()
	var archivePath, outputDir string
	var favorites []DirItem
	if cfg != nil {
		outputDir = cfg.OutputDir
		if cfg.DownloadArchive {
			archivePath = cfg.ArchivePath()
		}
		favorites = buildFavorites(cfg.FavoriteDirs)
	}

	return Model{
		ctx:          ctx,
		screen:       ScreenDepCheck,
		input:        ti,
		dirInput:     di,
		spin:         s,
		progModel:    p,
		progressCh:   make(chan ytdlp.ProgressEvent, 64),
		depCheckDone: false,
		archivePath:  archivePath,
		outputDir:    outputDir,
		favoriteDirs: favorites,
		mediaType:    MediaAudio, // default to audio for speed
		qualityIdx:   2,          // 1080p
		dashCursor:   dashMediaType,
	}
}

func (m Model) Init() tea.Cmd {
	return tea.Batch(textinput.Blink, m.spin.Tick, depCheckCmd())
}

// ── Update ──────────────────────────────────────────────────

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		w := msg.Width - 8
		if w < 30 {
			w = 30
		}
		if w > 80 {
			w = 80
		}
		m.input.Width = w
		m.dirInput.Width = w
		m.progModel.Width = msg.Width - 10
		if m.progModel.Width < 20 {
			m.progModel.Width = 20
		}
		return m, nil

	case tea.KeyMsg:
		m2, cmd := m.handleKeyMsg(msg)
		m = m2.(Model)

		// Forward key events to active text inputs
		switch m.screen {
		case ScreenInput:
			var ic tea.Cmd
			m.input, ic = m.input.Update(msg)
			return m, tea.Batch(cmd, ic)
		case ScreenDirPickerOverlay:
			if m.dirShowCustom {
				var ic tea.Cmd
				m.dirInput, ic = m.dirInput.Update(msg)
				return m, tea.Batch(cmd, ic)
			}
		}
		return m, cmd

	case depCheckResultMsg:
		m.depCheckDone = true
		m.ytdlpAvailable = msg.ytdlpOK
		m.ffmpegAvailable = msg.ffmpegOK
		m.partFiles = msg.partFiles
		if m.ytdlpAvailable {
			m.screen = ScreenInput
			m.input.Focus()
		} else {
			m.screen = ScreenDepCheck
		}
		return m, nil

	case metadataMsg:
		m.loading = false
		m.meta = msg.meta
		m.startDownloadAfterMetadata()
		return m, m.startDownloadCmd()

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
		return m, waitForProgressCmd(m.progressCh)

	case progressMsg:
		m.updateProgressFromEvent(msg.ProgressEvent)
		return m, waitForProgressCmd(m.progressCh)

	case downloadCompleteMsg:
		m.downloadOK = true
		m.finalPath = msg.outputPath
		m.finalSpeed = m.progress.Speed
		dur := time.Since(m.downloadStart).Truncate(time.Second)
		m.finalDuration = dur.String()
		m.screen = ScreenComplete
		return m, nil
	}

	var cmd tea.Cmd
	m.spin, cmd = m.spin.Update(msg)
	// Forward to input text fields on their screens
	if m.screen == ScreenInput {
		var ic tea.Cmd
		m.input, ic = m.input.Update(msg)
		return m, tea.Batch(cmd, ic)
	}
	if m.screen == ScreenDirPickerOverlay && m.dirShowCustom {
		var ic tea.Cmd
		m.dirInput, ic = m.dirInput.Update(msg)
		return m, tea.Batch(cmd, ic)
	}
	return m, cmd
}

// ── Key handling ────────────────────────────────────────────

func (m Model) handleKeyMsg(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "ctrl+c":
		return m, tea.Quit

	case "ctrl+d":
		if m.screen == ScreenConfigDashboard {
			return m, m.beginDownload()
		}

	case "q":
		if m.screen == ScreenInput || m.screen == ScreenDirPickerOverlay {
			// Don't quit on input screens
		} else {
			return m, tea.Quit
		}

	case "enter":
		return m.handleEnter()

	case "tab", "down", "j":
		if m.screen == ScreenConfigDashboard {
			m.dashCursorNext()
			return m, nil
		}
		if m.screen == ScreenDirPickerOverlay {
			m.dirPickerDown()
			return m, nil
		}
		if m.screen == ScreenResults {
			if m.cursor < len(m.searchResults)-1 {
				m.cursor++
			}
			return m, nil
		}

	case "shift+tab", "up", "k":
		if m.screen == ScreenConfigDashboard {
			m.dashCursorPrev()
			return m, nil
		}
		if m.screen == ScreenDirPickerOverlay {
			m.dirPickerUp()
			return m, nil
		}
		if m.screen == ScreenResults {
			if m.cursor > 0 {
				m.cursor--
			}
			return m, nil
		}

	case "left", "h":
		if m.screen == ScreenConfigDashboard {
			m.dashToggleLeft()
			return m, nil
		}

	case "right", "l":
		if m.screen == ScreenConfigDashboard {
			m.dashToggleRight()
			return m, nil
		}

	case "esc":
		if m.screen == ScreenDirPickerOverlay {
			m.dirPickerActive = false
			m.screen = ScreenConfigDashboard
			m.dirShowCustom = false
			m.dirInput.Blur()
		}

	case "r":
		switch m.screen {
		case ScreenDepCheck:
			return m, depCheckCmd()
		case ScreenError:
			m.err = nil
			m.screen = ScreenInput
			m.input.Focus()
			m.input.SetValue("")
		case ScreenComplete:
			m.resetForNewDownload()
		}

	case "o":
		if m.screen == ScreenComplete && m.finalPath != "" {
			openFolder(m.finalPath)
		}

	// Cookie auto-fix on error screen
	case "b":
		if m.screen == ScreenError && ytdlp.IsBotError(m.err) {
			m.saveCookiesConfig("brave")
			return m, m.retryWithCookies()
		}
	case "c":
		if m.screen == ScreenError && ytdlp.IsBotError(m.err) {
			m.saveCookiesConfig("chrome")
			return m, m.retryWithCookies()
		}
	case "f":
		if m.screen == ScreenError && ytdlp.IsBotError(m.err) {
			m.saveCookiesConfig("firefox")
			return m, m.retryWithCookies()
		}
	}

	return m, nil
}

// ── Dashboard navigation helpers ────────────────────────────

func (m *Model) dashCursorNext() {
	for i := 1; i <= int(dashFieldCount); i++ {
		next := (int(m.dashCursor) + i) % int(dashFieldCount)
		f := dashField(next)
		if m.dashFieldVisible(f) {
			m.dashCursor = f
			return
		}
	}
}

func (m *Model) dashCursorPrev() {
	for i := 1; i <= int(dashFieldCount); i++ {
		prev := (int(m.dashCursor) - i + int(dashFieldCount)) % int(dashFieldCount)
		f := dashField(prev)
		if m.dashFieldVisible(f) {
			m.dashCursor = f
			return
		}
	}
}

func (m *Model) dashFieldVisible(f dashField) bool {
	switch f {
	case dashQuality:
		return m.mediaType == MediaVideo
	case dashTrimStart, dashTrimEnd:
		return m.trimEnabled
	default:
		return true
	}
}

func (m *Model) dashToggleLeft() {
	switch m.dashCursor {
	case dashMediaType:
		if m.mediaType > MediaVideo {
			m.mediaType--
		}
	case dashQuality:
		if m.qualityIdx > 0 {
			m.qualityIdx--
		}
	case dashTrim:
		m.trimEnabled = !m.trimEnabled
	}
}

func (m *Model) dashToggleRight() {
	switch m.dashCursor {
	case dashMediaType:
		if m.mediaType < MediaAudio {
			m.mediaType++
		}
	case dashQuality:
		if m.qualityIdx < len(qualityPresets)-1 {
			m.qualityIdx++
		}
	case dashTrim:
		m.trimEnabled = !m.trimEnabled
	}
}

func (m *Model) dirPickerUp() {
	if !m.dirShowCustom && m.dirCursor > 0 {
		m.dirCursor--
	}
}

func (m *Model) dirPickerDown() {
	if !m.dirShowCustom {
		total := len(m.dirFavorites)
		if total > 0 && m.dirCursor < total-1 {
			m.dirCursor++
		}
	}
}

func (m Model) handleEnter() (tea.Model, tea.Cmd) {
	switch m.screen {
	case ScreenDepCheck:
		if m.ytdlpAvailable {
			m.screen = ScreenInput
			m.input.Focus()
		}
		return m, nil

	case ScreenInput:
		q := strings.TrimSpace(m.input.Value())
		if q == "" {
			return m, nil
		}
		m.query = q
		m.loading = true

		if urlRegex.MatchString(q) {
			// URL → go directly to config dashboard
			m.loading = false
			m.screen = ScreenConfigDashboard
			m.dashCursor = dashMediaType
			m.input.Blur()
			return m, nil
		}
		// Search query → show results first
		m.inputMode = InputSearch
		m.loadingMsg = "Searching..."
		m.input.Blur()
		return m, searchCmd(m.ctx, q, m.cookiesFile, m.cookiesFromBrowser)

	case ScreenResults:
		if m.cursor < len(m.searchResults) {
			m.query = m.searchResults[m.cursor].URL
			m.screen = ScreenConfigDashboard
			m.dashCursor = dashMediaType
		}
		return m, nil

	case ScreenConfigDashboard:
		switch m.dashCursor {
		case dashSaveLocation:
			// Open dir picker overlay
			m.screen = ScreenDirPickerOverlay
			m.dirPickerActive = true
			m.dirCursor = 0
			m.dirShowCustom = false
			m.buildDirItems()
		case dashStartDownload:
			return m, m.beginDownload()
		default:
			// Treat Enter like Right arrow on other fields
			m.dashToggleRight()
		}
		return m, nil

	case ScreenDirPickerOverlay:
		if m.dirShowCustom {
			path := strings.TrimSpace(m.dirInput.Value())
			if path != "" {
				m.outputDir = expandPath(path)
			}
			m.dirPickerActive = false
			m.screen = ScreenConfigDashboard
			return m, nil
		}
		if m.dirCursor < len(m.dirFavorites) {
			item := m.dirFavorites[m.dirCursor]
			if item.IsCustom {
				m.dirShowCustom = true
				m.dirInput.Focus()
				m.dirInput.SetValue("")
				return m, nil
			}
			m.outputDir = item.Path
		}
		m.dirPickerActive = false
		m.screen = ScreenConfigDashboard
		return m, nil

	case ScreenComplete:
		m.resetForNewDownload()
		return m, nil
	}

	return m, nil
}

// openFolder opens the parent directory of the given file in the file manager.
func openFolder(path string) {
	dir := filepath.Dir(path)
	switch runtime.GOOS {
	case "linux":
		exec.Command("xdg-open", dir).Start()
	case "darwin":
		exec.Command("open", dir).Start()
	case "windows":
		exec.Command("explorer", dir).Start()
	}
}

// ── Download flow ───────────────────────────────────────────

func (m *Model) beginDownload() tea.Cmd {
	url := m.query

	if !urlRegex.MatchString(url) && len(m.searchResults) > 0 && m.cursor < len(m.searchResults) {
		url = m.searchResults[m.cursor].URL
	}

	if !urlRegex.MatchString(url) {
		return func() tea.Msg {
			return errMsg{fmt.Errorf("no valid URL. Enter a URL on the input screen first.")}
		}
	}

	m.loading = true
	m.loadingMsg = "Fetching video info..."
	m.screen = ScreenProgress
	m.downloadStart = time.Now()

	// Fetch metadata first (gives us title for display + validates URL)
	return fetchMetadataCmd(m.ctx, url, m.cookiesFile, m.cookiesFromBrowser)
}

// Called after metadata arrives — builds the final ytdlp options and starts download.
func (m *Model) startDownloadAfterMetadata() {
	url := m.meta.URL
	if url == "" {
		url = m.query
	}

	format := "mp4"
	quality := qualityValues[m.qualityIdx]

	if m.mediaType == MediaAudio {
		format = "mp3"
		quality = "best"
	}

	opts := ytdlp.Options{
		URL:                url,
		Format:             format,
		Quality:            quality,
		Output:             m.outputDir,
		Subtitles:          false,
		TrimStart:          m.trimStart,
		TrimEnd:            m.trimEnd,
		ArchivePath:        m.archivePath,
		CookiesFile:        m.cookiesFile,
		CookiesFromBrowser: m.cookiesFromBrowser,
	}

	m.formatOpts = []ytdlp.Options{opts}
}

func (m *Model) startDownloadCmd() tea.Cmd {
	if len(m.formatOpts) == 0 {
		return func() tea.Msg {
			return errMsg{fmt.Errorf("no download options resolved")}
		}
	}
	return startDownloadCmd(m.ctx, m.formatOpts[0], m.progressCh)
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

// ── Helpers ─────────────────────────────────────────────────

func (m *Model) saveCookiesConfig(browser string) {
	m.cookiesFromBrowser = browser
	m.cookiesFile = ""
	if cfg, err := config.Load(); err == nil {
		cfg.CookiesFromBrowser = browser
		cfg.CookiesFile = ""
		_ = cfg.Save()
	}
}

func (m *Model) retryWithCookies() tea.Cmd {
	m.err = nil
	m.screen = ScreenInput
	m.input.Focus()
	m.input.SetValue(m.query)
	return nil
}

func (m *Model) resetForNewDownload() {
	m.screen = ScreenInput
	m.query = ""
	m.err = nil
	m.downloadOK = false
	m.finalPath = ""
	m.finalSpeed = ""
	m.finalDuration = ""
	m.meta = nil
	m.progress = DownloadProgress{}
	m.progressBar = 0
	m.input.Focus()
	m.input.SetValue("")
	// Keep cookies, output dir, favorites, dashboard config values
}

func (m *Model) buildDirItems() {
	items := make([]DirItem, 0, len(m.favoriteDirs)+2)
	for _, d := range m.favoriteDirs {
		items = append(items, d)
	}
	// Add config output dir if not already in favorites
	hasOutput := false
	for _, d := range items {
		if d.Path == m.outputDir {
			hasOutput = true
			break
		}
	}
	if !hasOutput && m.outputDir != "" {
		items = append(items, DirItem{Label: "Default: " + m.outputDir, Path: m.outputDir})
	}
	items = append(items, DirItem{Label: "[ Custom path ]", Path: "", IsCustom: true})
	m.dirFavorites = items
}

func buildFavorites(cfgDirs []string) []DirItem {
	if len(cfgDirs) == 0 {
		cfgDirs = []string{"~/Downloads", "~/Videos", "~/Music"}
	}
	items := make([]DirItem, 0, len(cfgDirs))
	for _, d := range cfgDirs {
		d = strings.TrimSpace(d)
		if d == "" {
			continue
		}
		expanded := expandPath(d)
		items = append(items, DirItem{
			Label: d,
			Path:  expanded,
		})
	}
	return items
}

func expandPath(path string) string {
	if strings.HasPrefix(path, "~/") {
		home, err := os.UserHomeDir()
		if err == nil {
			return filepath.Join(home, path[2:])
		}
	}
	return path
}

func truncateStr(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
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

// ── View ────────────────────────────────────────────────────

func (m Model) View() string {
	if m.done {
		return ""
	}
	switch m.screen {
	case ScreenDepCheck:
		return m.viewDepCheck()
	case ScreenInput:
		return m.viewInput()
	case ScreenResults:
		return m.viewResults()
	case ScreenConfigDashboard:
		return m.viewConfigDashboard()
	case ScreenDirPickerOverlay:
		return m.viewDirPicker()
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

var _ tea.Model = Model{}
