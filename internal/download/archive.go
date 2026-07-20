// Package download manages download archive tracking and session resume.
package download

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Archive tracks already-downloaded videos via a text file.
// Each line contains "extractor video_id" (yt-dlp archive format).
type Archive struct {
	path    string
	entries map[string]bool
	dirty   bool
}

// NewArchive opens or creates an archive file at the given path.
// If path is empty, returns a no-op archive.
func NewArchive(path string) (*Archive, error) {
	a := &Archive{
		path:    path,
		entries: make(map[string]bool),
	}

	if path == "" {
		return a, nil
	}

	// Ensure parent dir exists
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("create archive dir: %w", err)
	}

	// Read existing entries
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return a, nil
		}
		return nil, fmt.Errorf("open archive: %w", err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line != "" && !strings.HasPrefix(line, "#") {
			a.entries[line] = true
		}
	}

	return a, scanner.Err()
}

// Contains checks if a video ID is in the archive.
// identifier format: "youtube dQw4w9WgXcQ"
func (a *Archive) Contains(extractor, id string) bool {
	key := a.makeKey(extractor, id)
	return a.entries[key]
}

// Add records a video ID as downloaded.
func (a *Archive) Add(extractor, id string) error {
	if a.path == "" {
		return nil
	}

	key := a.makeKey(extractor, id)
	if a.entries[key] {
		return nil // already recorded
	}

	f, err := os.OpenFile(a.path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return fmt.Errorf("append archive: %w", err)
	}
	defer f.Close()

	if _, err := fmt.Fprintf(f, "%s\n", key); err != nil {
		return fmt.Errorf("write archive: %w", err)
	}

	a.entries[key] = true
	return nil
}

// Path returns the archive file path.
func (a *Archive) Path() string {
	return a.path
}

// Count returns number of entries in the archive.
func (a *Archive) Count() int {
	return len(a.entries)
}

func (a *Archive) makeKey(extractor, id string) string {
	return fmt.Sprintf("%s %s", extractor, id)
}

// ── Part file scanning ────────────────────────────────────────

// PartFile represents an incomplete download.
type PartFile struct {
	Path string
	Size int64
}

// ScanPartFiles finds .part files in the given directory recursively.
func ScanPartFiles(dir string) ([]PartFile, error) {
	var parts []PartFile

	err := filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil // skip unreadable
		}
		if d.IsDir() {
			return nil
		}
		if strings.HasSuffix(d.Name(), ".part") {
			info, err := d.Info()
			if err != nil {
				return nil
			}
			parts = append(parts, PartFile{
				Path: path,
				Size: info.Size(),
			})
		}
		return nil
	})

	return parts, err
}

// PartFileInfo returns a human-readable summary of part files.
func PartFileInfo(parts []PartFile) string {
	if len(parts) == 0 {
		return ""
	}
	var totalSize int64
	names := make([]string, 0, len(parts))
	for _, p := range parts {
		totalSize += p.Size
		names = append(names, filepath.Base(p.Path))
	}
	return fmt.Sprintf("%d incomplete file(s): %s (%s)",
		len(parts),
		strings.Join(names, ", "),
		formatBytes(totalSize),
	)
}

func formatBytes(b int64) string {
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
