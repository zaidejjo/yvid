// Package ytdlp provides a subprocess wrapper around the yt-dlp binary.
//
// It spawns yt-dlp, streams progress via JSON template output,
// fetches video metadata, and returns structured progress records.
package ytdlp

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os/exec"
	"strings"
)

// ── Types ──────────────────────────────────────────────────────

// Options defines parameters for a yt-dlp download.
type Options struct {
	URL       string
	Format    string // mp4 or mp3
	Quality   string // best, 2160p, 1080p, 720p, 480p
	Output    string // output directory
	Subtitles bool
	TrimStart string
	TrimEnd   string
}

// VideoMetadata holds selected fields from yt-dlp --dump-json.
type VideoMetadata struct {
	ID        string   `json:"id"`
	Title     string   `json:"title"`
	URL       string   `json:"webpage_url"`
	Duration  float64  `json:"duration"`
	Thumbnail string   `json:"thumbnail"`
	Uploader  string   `json:"uploader"`
	ViewCount int64    `json:"view_count"`
	Extractor string   `json:"extractor"`
	Formats   []Format `json:"formats"`
}

// Format represents a single downloadable format from yt-dlp.
type Format struct {
	FormatID       string  `json:"format_id"`
	Ext            string  `json:"ext"`
	Resolution     string  `json:"resolution"`
	Filesize       int64   `json:"filesize"`
	FilesizeApprox int64   `json:"filesize_approx"`
	VideoBitrate   float64 `json:"vbr"`
	AudioBitrate   float64 `json:"abr"`
	FormatNote     string  `json:"format_note"`
	Height         int     `json:"height"`
	Width          int     `json:"width"`
	FPS            float64 `json:"fps"`
}

// SearchResultItem represents one result from ytsearch.
type SearchResultItem struct {
	ID        string  `json:"id"`
	Title     string  `json:"title"`
	URL       string  `json:"webpage_url"`
	Duration  float64 `json:"duration"`
	Uploader  string  `json:"uploader"`
	ViewCount int64   `json:"view_count"`
	Thumbnail string  `json:"thumbnail"`
}

// ProgressEvent represents a single progress update from yt-dlp.
type ProgressEvent struct {
	Status     string // downloading, post_processing, completed, error
	Percent    float64
	Speed      float64 // bytes per second
	ETA        float64 // seconds remaining
	Downloaded int64   // bytes
	Total      int64   // bytes
	OutputPath string
	Message    string // error message if Status == "error"
}

// ── Downloader ─────────────────────────────────────────────────

// Downloader manages yt-dlp subprocesses.
type Downloader struct {
	binary string
}

// NewDownloader creates a Downloader, finding yt-dlp in PATH.
func NewDownloader() *Downloader {
	return &Downloader{binary: "yt-dlp"}
}

// SetBinary overrides the yt-dlp binary path (useful for testing).
func (d *Downloader) SetBinary(path string) {
	d.binary = path
}

// ── Metadata / Search ──────────────────────────────────────────

// FetchMetadata retrieves video metadata via yt-dlp --dump-json.
func (d *Downloader) FetchMetadata(ctx context.Context, url string) (*VideoMetadata, error) {
	args := []string{
		"--dump-json",
		"--no-download",
		"--no-playlist",
		"--no-warnings",
		url,
	}

	cmd := exec.CommandContext(ctx, d.binary, args...)
	output, err := cmd.Output()
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			return nil, fmt.Errorf("yt-dlp metadata: %s", strings.TrimSpace(string(exitErr.Stderr)))
		}
		return nil, fmt.Errorf("yt-dlp metadata: %w", err)
	}

	var meta VideoMetadata
	if err := json.Unmarshal(output, &meta); err != nil {
		return nil, fmt.Errorf("parse metadata: %w", err)
	}

	return &meta, nil
}

// Search performs a YouTube search via ytsearch5: and returns results.
func (d *Downloader) Search(ctx context.Context, query string) ([]SearchResultItem, error) {
	args := []string{
		"--dump-json",
		"--no-download",
		"--no-playlist",
		"--no-warnings",
		"--flat-playlist",
		fmt.Sprintf("ytsearch5:%s", query),
	}

	cmd := exec.CommandContext(ctx, d.binary, args...)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, fmt.Errorf("stdout pipe: %w", err)
	}

	var stderrBuf strings.Builder
	cmd.Stderr = &stderrBuf

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("start yt-dlp search: %w", err)
	}

	var results []SearchResultItem
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 0, 64*1024), 64*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var item SearchResultItem
		if err := json.Unmarshal([]byte(line), &item); err != nil {
			continue // skip malformed lines
		}
		if item.Title != "" {
			results = append(results, item)
		}
	}

	if err := cmd.Wait(); err != nil {
		stderr := strings.TrimSpace(stderrBuf.String())
		if stderr == "" {
			stderr = err.Error()
		}
		return results, fmt.Errorf("yt-dlp search: %s", stderr)
	}

	if len(results) == 0 {
		return nil, fmt.Errorf("no results for query: %s", query)
	}

	return results, nil
}

// ── Progress helpers ──────────────────────────────────────────

// PercentBar returns a simple bar string like "████████░░ 80%".
func (p *ProgressEvent) PercentBar() string {
	const width = 20
	filled := int(p.Percent / 100.0 * width)
	if filled > width {
		filled = width
	}
	return fmt.Sprintf("%s%s %3.0f%%",
		strings.Repeat("█", filled),
		strings.Repeat("░", width-filled),
		p.Percent,
	)
}

// SpeedHuman returns a human-readable speed string.
func (p *ProgressEvent) SpeedHuman() string {
	if p.Speed <= 0 {
		return "---"
	}
	switch {
	case p.Speed >= 1_000_000:
		return fmt.Sprintf("%.1f MB", p.Speed/1_000_000)
	case p.Speed >= 1_000:
		return fmt.Sprintf("%.0f KB", p.Speed/1_000)
	default:
		return fmt.Sprintf("%.0f B", p.Speed)
	}
}

// ETAHuman returns a human-readable ETA string.
func (p *ProgressEvent) ETAHuman() string {
	if p.ETA <= 0 {
		return "---"
	}
	if p.ETA >= 3600 {
		return fmt.Sprintf("%.0fh%02.0fm", p.ETA/3600, p.ETA/60)
	}
	if p.ETA >= 60 {
		return fmt.Sprintf("%.0fm%02.0fs", p.ETA/60, float64(int(p.ETA)%60))
	}
	return fmt.Sprintf("%.0fs", p.ETA)
}

// ── Download ───────────────────────────────────────────────────

// Download spawns yt-dlp as a subprocess and returns a channel of progress events.
// The caller must consume the channel until it closes.
func (d *Downloader) Download(ctx context.Context, opts Options) (<-chan ProgressEvent, error) {
	args := d.buildArgs(opts)

	cmd := exec.CommandContext(ctx, d.binary, args...)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, fmt.Errorf("stdout pipe: %w", err)
	}

	stderr, err := cmd.StderrPipe()
	if err != nil {
		return nil, fmt.Errorf("stderr pipe: %w", err)
	}

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("start yt-dlp: %w", err)
	}

	ch := make(chan ProgressEvent, 64)

	go func() {
		defer close(ch)
		d.parseOutput(ctx, stdout, ch)
	}()

	go func() {
		// Read stderr for debugging (yt-dlp logs errors there)
		slurp, _ := io.ReadAll(stderr)
		if len(slurp) > 0 {
			ch <- ProgressEvent{Status: "error", Message: strings.TrimSpace(string(slurp))}
		}
	}()

	go func() {
		if err := cmd.Wait(); err != nil {
			if exitErr, ok := err.(*exec.ExitError); ok {
				ch <- ProgressEvent{Status: "error", Message: fmt.Sprintf("yt-dlp exited with code %d", exitErr.ExitCode())}
			} else {
				ch <- ProgressEvent{Status: "error", Message: err.Error()}
			}
		}
	}()

	return ch, nil
}

// ── Arg building ───────────────────────────────────────────────

func (d *Downloader) buildArgs(opts Options) []string {
	args := []string{
		"--no-playlist",
		"--no-warnings",
		"--newline",
		"--progress-template",
		`json:{"status":"downloading","percent":"%(progress.percent)s","speed":"%(progress.speed)s","eta":"%(progress.eta)s","downloaded":"%(progress.downloaded_bytes)s","total":"%(progress.total_bytes)s"}`,
	}

	// Output template
	outputDir := opts.Output
	if outputDir == "" {
		outputDir = "."
	}
	args = append(args, "-o", fmt.Sprintf("%s/%%(title)s.%%(ext)s", outputDir))

	// Format selection
	switch opts.Format {
	case "mp3":
		args = append(args, "-f", "bestaudio/bestvideo+bestaudio/best",
			"--extract-audio", "--audio-format", "mp3", "--audio-quality", "192K")
	case "mp4":
		fallthrough
	default:
		quality := opts.Quality
		if quality == "" {
			quality = "1080p"
		}

		var formatStr string
		switch quality {
		case "best":
			formatStr = "bestvideo+bestaudio/best"
		case "2160p":
			formatStr = "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best"
		case "1080p":
			formatStr = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
		case "720p":
			formatStr = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
		case "480p":
			formatStr = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
		default:
			formatStr = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
		}
		args = append(args, "-f", formatStr, "--merge-output-format", "mp4",
			"--postprocessor-args", "ffmpeg:-movflags +faststart")
	}

	// Subtitles
	if opts.Subtitles {
		args = append(args,
			"--write-subs",
			"--write-auto-subs",
			"--sub-langs", "en,ar",
			"--sub-format", "srt",
			"--embed-subs",
		)
	}

	// Trim
	if opts.TrimStart != "" || opts.TrimEnd != "" {
		trimArgs := buildTrimArgs(opts.TrimStart, opts.TrimEnd)
		if trimArgs != "" {
			args = append(args, "--postprocessor-args", fmt.Sprintf("ffmpeg:%s", trimArgs))
		}
	}

	args = append(args, opts.URL)
	return args
}

func buildTrimArgs(start, end string) string {
	var parts []string
	if start != "" {
		parts = append(parts, "-ss", start)
	}
	if end != "" {
		parts = append(parts, "-to", end)
	}
	return strings.Join(parts, " ")
}

// ── Output parsing ─────────────────────────────────────────────

func (d *Downloader) parseOutput(ctx context.Context, r io.Reader, ch chan<- ProgressEvent) {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 0, 64*1024), 64*1024)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		evt := parseProgressLine(line)
		select {
		case ch <- evt:
		case <-ctx.Done():
			return
		}
	}
}

// DurationStr formats duration in seconds to "H:MM:SS".
func DurationStr(seconds float64) string {
	if seconds <= 0 {
		return "--:--"
	}
	h := int(seconds) / 3600
	m := (int(seconds) % 3600) / 60
	s := int(seconds) % 60
	if h > 0 {
		return fmt.Sprintf("%d:%02d:%02d", h, m, s)
	}
	return fmt.Sprintf("%d:%02d", m, s)
}
