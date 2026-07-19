// Package ffmpeg wraps FFmpeg subprocess calls for video trimming.
package ffmpeg

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const (
	trimTimeout   = 5 * time.Minute
	maxErrorLines = 200
)

// TrimOptions specifies the trim operation parameters.
type TrimOptions struct {
	InputPath  string
	OutputPath string
	StartTime  string // HH:MM:SS or SS
	EndTime    string // HH:MM:SS or SS
}

// Trim cuts a video segment using FFmpeg stream copy (no re-encode).
// The operation is lossless and near-instant.
func Trim(ctx context.Context, opts TrimOptions) error {
	if err := checkFFmpeg(); err != nil {
		return err
	}

	// Validate input file
	if _, err := os.Stat(opts.InputPath); os.IsNotExist(err) {
		return fmt.Errorf("input file not found: %s", opts.InputPath)
	}

	// Generate output path if not provided
	outputPath := opts.OutputPath
	if outputPath == "" {
		ext := filepath.Ext(opts.InputPath)
		base := strings.TrimSuffix(opts.InputPath, ext)
		outputPath = base + "_trimmed" + ext
	}

	args := []string{"-i", opts.InputPath, "-c", "copy", "-map", "0"}
	if opts.StartTime != "" {
		args = append(args, "-ss", opts.StartTime)
	}
	if opts.EndTime != "" {
		args = append(args, "-to", opts.EndTime)
	}
	args = append(args, "-y", outputPath)

	// Create context with timeout
	ctx, cancel := context.WithTimeout(ctx, trimTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "ffmpeg", args...)

	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return fmt.Errorf("trim timed out after %v", trimTimeout)
		}

		// Extract relevant error info
		errOutput := stderr.String()
		if len(errOutput) > maxErrorLines {
			lines := strings.Split(errOutput, "\n")
			errOutput = strings.Join(lines[len(lines)-maxErrorLines:], "\n")
		}

		return fmt.Errorf("ffmpeg trim failed: %s", truncate(errOutput, 500))
	}

	// Verify output was created
	if _, err := os.Stat(outputPath); os.IsNotExist(err) {
		return fmt.Errorf("trim produced no output file")
	}

	return nil
}

// ReplaceOriginal replaces the original file with the trimmed version.
func ReplaceOriginal(original, trimmed string) error {
	if err := os.Rename(trimmed, original); err != nil {
		return fmt.Errorf("replace original: %w", err)
	}
	return nil
}

// Available checks if ffmpeg is installed and reachable.
func Available() bool {
	return checkFFmpeg() == nil
}

func checkFFmpeg() error {
	_, err := exec.LookPath("ffmpeg")
	if err != nil {
		return fmt.Errorf("ffmpeg not found in PATH; install from https://ffmpeg.org")
	}
	return nil
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
