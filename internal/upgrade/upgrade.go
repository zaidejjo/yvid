// Package upgrade handles self-upgrading yvid from GitHub Releases.
package upgrade

import (
	"archive/tar"
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

const (
	ghAPI = "https://api.github.com/repos/%s/releases/latest"
)

// Manager handles checking for and applying updates.
type Manager struct {
	repo    string // "owner/repo"
	current string // current version (e.g. "1.2.0")
	client  *http.Client
}

// Release represents a GitHub release.
type Release struct {
	TagName string  `json:"tag_name"`
	Assets  []Asset `json:"assets"`
}

// Asset represents a GitHub release asset.
type Asset struct {
	Name        string `json:"name"`
	DownloadURL string `json:"browser_download_url"`
}

// NewManager creates an upgrade manager.
func NewManager(repo, currentVersion string) *Manager {
	return &Manager{
		repo:    repo,
		current: currentVersion,
		client:  http.DefaultClient,
	}
}

// Check queries GitHub for the latest release.
// Returns true if a newer version exists, along with the version string.
func (m *Manager) Check() (bool, string, error) {
	url := fmt.Sprintf(ghAPI, m.repo)

	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, url, nil)
	if err != nil {
		return false, "", err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := m.client.Do(req)
	if err != nil {
		return false, "", fmt.Errorf("fetch release: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == 404 {
		return false, "", fmt.Errorf("repo not found: %s", m.repo)
	}
	if resp.StatusCode != http.StatusOK {
		return false, "", fmt.Errorf("GitHub API returned %d", resp.StatusCode)
	}

	var release Release
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		return false, "", fmt.Errorf("parse release: %w", err)
	}

	latestVer := strings.TrimPrefix(release.TagName, "v")
	currentVer := strings.TrimPrefix(m.current, "v")

	if latestVer == currentVer {
		return false, latestVer, nil
	}

	// Simple comparison: different version means update available
	// In production, use semver.Compare
	return true, latestVer, nil
}

// Upgrade downloads and installs the latest binary.
func (m *Manager) Upgrade() error {
	url := fmt.Sprintf(ghAPI, m.repo)

	req, _ := http.NewRequestWithContext(context.Background(), http.MethodGet, url, nil)
	req.Header.Set("Accept", "application/json")

	resp, err := m.client.Do(req)
	if err != nil {
		return fmt.Errorf("fetch release: %w", err)
	}
	defer resp.Body.Close()

	var release Release
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		return fmt.Errorf("parse release: %w", err)
	}

	// Find matching asset for current OS/arch
	assetName := m.assetName()
	var targetAsset Asset
	for _, a := range release.Assets {
		if strings.Contains(a.Name, assetName) {
			targetAsset = a
			break
		}
	}
	if targetAsset.DownloadURL == "" {
		return fmt.Errorf("no binary found for %s (expected: %s)", runtime.GOOS+"/"+runtime.GOARCH, assetName)
	}

	return m.install(targetAsset.DownloadURL)
}

func (m *Manager) install(downloadURL string) error {
	req, _ := http.NewRequestWithContext(context.Background(), http.MethodGet, downloadURL, nil)
	resp, err := m.client.Do(req)
	if err != nil {
		return fmt.Errorf("download: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download returned %d", resp.StatusCode)
	}

	// Get current binary path
	execPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("cannot determine executable path: %w", err)
	}

	// Download to temp file
	tmpPath := execPath + ".tmp"
	f, err := os.OpenFile(tmpPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o755)
	if err != nil {
		return fmt.Errorf("create temp: %w", err)
	}

	var reader io.Reader = resp.Body

	// Handle gzip/tar.gz
	contentType := resp.Header.Get("Content-Type")
	contentDisposition := resp.Header.Get("Content-Disposition")

	if strings.Contains(contentType, "gzip") || strings.HasSuffix(downloadURL, ".gz") ||
		strings.Contains(contentDisposition, ".gz") || strings.HasSuffix(downloadURL, ".tar.gz") {
		gr, err := gzip.NewReader(resp.Body)
		if err != nil {
			f.Close()
			os.Remove(tmpPath)
			return fmt.Errorf("gzip reader: %w", err)
		}
		defer gr.Close()

		tr := tar.NewReader(gr)
		for {
			hdr, err := tr.Next()
			if err == io.EOF {
				break
			}
			if err != nil {
				f.Close()
				os.Remove(tmpPath)
				return fmt.Errorf("tar reader: %w", err)
			}
			// Find binary inside archive (skip dirs, non-binaries)
			if hdr.FileInfo().IsDir() || !strings.Contains(hdr.Name, "yvid") ||
				strings.HasSuffix(hdr.Name, ".md") || strings.HasSuffix(hdr.Name, ".txt") {
				continue
			}
			if _, err := io.Copy(f, tr); err != nil {
				f.Close()
				os.Remove(tmpPath)
				return fmt.Errorf("extract binary: %w", err)
			}
			break
		}
	} else {
		if _, err := io.Copy(f, reader); err != nil {
			f.Close()
			os.Remove(tmpPath)
			return fmt.Errorf("write temp: %w", err)
		}
	}

	f.Close()

	// Replace original binary
	if err := os.Rename(tmpPath, execPath); err != nil {
		// Fallback: copy then remove
		if err2 := copyFile(tmpPath, execPath); err2 != nil {
			os.Remove(tmpPath)
			return fmt.Errorf("replace binary: %w (copy fallback: %v)", err, err2)
		}
		os.Remove(tmpPath)
	}

	return nil
}

func (m *Manager) assetName() string {
	arch := runtime.GOARCH
	switch arch {
	case "amd64":
		arch = "x86_64"
	case "arm64":
		arch = "aarch64"
	}

	osName := runtime.GOOS
	switch osName {
	case "darwin":
		osName = "macos"
	case "windows":
		osName = "windows"
	}

	return fmt.Sprintf("yvid_%s_%s", osName, arch)
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.OpenFile(dst, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o755)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}

// ExecPath returns the directory of the current binary (for install scripts).
func ExecPath() (string, error) {
	return os.Executable()
}

// DownloadDir returns the recommended download directory.
func DownloadDir() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return filepath.Join("/tmp", "yvid-upgrade")
	}
	return filepath.Join(home, ".cache", "yvid", "upgrade")
}
