// Package ytdlp provides a subprocess wrapper around the yt-dlp binary.
//
// It spawns yt-dlp, streams progress via JSON template output,
// and returns structured progress records through a channel.
package ytdlp

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os/exec"
	"strings"
)

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

// buildArgs constructs the yt-dlp command-line arguments.
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

// parseOutput reads JSON progress lines from yt-dlp stdout.
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
