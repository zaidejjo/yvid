// Package upgrade handles self-upgrading yvid from GitHub Releases.
package upgrade

import (
	"archive/tar"
	"archive/zip"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"

	"golang.org/x/mod/semver"
)

const (
	ghAPI     = "https://api.github.com/repos/%s/releases/latest"
	ghRepo    = "zaidejjo/yvid"
	userAgent = "yvid-upgrade/1.0"
)

// Manager handles checking for and applying updates.
type Manager struct {
	repo    string
	current string
	client  *http.Client
	release *Release // cached after Check()
}

// Release represents a GitHub release.
type Release struct {
	TagName string  `json:"tag_name"`
	Assets  []Asset `json:"assets"`
	HTMLURL string  `json:"html_url"`
}

// Asset represents a GitHub release asset.
type Asset struct {
	Name        string `json:"name"`
	DownloadURL string `json:"browser_download_url"`
	Size        int64  `json:"size"`
}

// NewManager creates an upgrade manager.
func NewManager(repo, currentVersion string) *Manager {
	return &Manager{
		repo:    repo,
		current: strings.TrimPrefix(currentVersion, "v"),
		client:  &http.Client{},
	}
}

// Check queries GitHub for the latest release.
// Returns true, latest-version, nil if upgrade is available.
func (m *Manager) Check() (bool, string, error) {
	release, err := m.fetchLatestRelease()
	if err != nil {
		return false, "", err
	}
	m.release = release

	latestVer := strings.TrimPrefix(release.TagName, "v")

	// semver.Compare returns +1 if latest > current
	if semver.Compare("v"+latestVer, "v"+m.current) <= 0 {
		return false, latestVer, nil
	}

	return true, latestVer, nil
}

// Upgrade downloads and installs the latest binary.
// Must be called after Check() or will re-fetch.
func (m *Manager) Upgrade() error {
	// Fetch release if not cached
	if m.release == nil {
		release, err := m.fetchLatestRelease()
		if err != nil {
			return err
		}
		m.release = release
	}

	// Find matching asset
	asset, err := m.findAsset(m.release.Assets)
	if err != nil {
		return err
	}

	// Download and install
	execPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("cannot determine executable path: %w", err)
	}

	return m.install(asset, execPath)
}

// CheckAndUpgrade performs both steps atomically.
func (m *Manager) CheckAndUpgrade() (string, error) {
	available, version, err := m.Check()
	if err != nil {
		return "", fmt.Errorf("check failed: %w", err)
	}
	if !available {
		return "", fmt.Errorf("already up-to-date (%s)", m.current)
	}
	if err := m.Upgrade(); err != nil {
		return "", fmt.Errorf("upgrade failed: %w", err)
	}
	return version, nil
}

// ── Internal ──────────────────────────────────────────────────

func (m *Manager) fetchLatestRelease() (*Release, error) {
	url := fmt.Sprintf(ghAPI, m.repo)

	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", userAgent)

	resp, err := m.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetch release: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == 404 {
		return nil, fmt.Errorf("repository not found: %s", m.repo)
	}
	if resp.StatusCode == 403 {
		return nil, fmt.Errorf("GitHub API rate limit exceeded (unauthenticated requests limited to 60/hr)")
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GitHub API returned %d", resp.StatusCode)
	}

	var release Release
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		return nil, fmt.Errorf("parse release: %w", err)
	}

	if release.TagName == "" {
		return nil, fmt.Errorf("no releases found for %s", m.repo)
	}

	return &release, nil
}

// findAsset locates the archive matching current OS/arch.
// Asset naming from goreleaser:
//
//	yvid_<version>_<os>_<arch>.tar.gz   (linux/darwin)
//	yvid_<version>_<os>_<arch>.zip      (windows)
func (m *Manager) findAsset(assets []Asset) (*Asset, error) {
	// Goreleaser naming: yvid_<version>_<os>_<arch>.tar.gz
	// Match by OS/arch suffix within asset name.
	expectSuffix := m.assetSuffix() // "_linux_amd64" or "_windows_amd64"

	var candidates []Asset
	for _, a := range assets {
		if strings.Contains(a.Name, expectSuffix) {
			candidates = append(candidates, a)
		}
	}

	switch len(candidates) {
	case 0:
		return nil, fmt.Errorf("no binary found for %s/%s\n  available: %s",
			runtime.GOOS, runtime.GOARCH, listAssetNames(assets))
	case 1:
		return &candidates[0], nil
	default:
		// Prefer non-checksum assets (filter out checksums.txt, .sig)
		for _, a := range candidates {
			if strings.HasSuffix(a.Name, ".tar.gz") || strings.HasSuffix(a.Name, ".zip") {
				return &a, nil
			}
		}
		return &candidates[0], nil
	}
}

// install downloads, validates, and replaces the binary.
func (m *Manager) install(asset *Asset, execPath string) error {
	fmt.Fprintf(os.Stderr, "  Downloading %s...\n", asset.Name)

	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, asset.DownloadURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", userAgent)

	resp, err := m.client.Do(req)
	if err != nil {
		return fmt.Errorf("download: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download returned %d", resp.StatusCode)
	}

	// Create temp directory
	tmpDir, err := os.MkdirTemp("", "yvid-upgrade-*")
	if err != nil {
		return fmt.Errorf("create temp dir: %w", err)
	}
	defer os.RemoveAll(tmpDir)

	// Determine extraction method
	var binaryPath string
	if strings.HasSuffix(asset.Name, ".zip") {
		binaryPath, err = extractZip(resp.Body, tmpDir)
	} else {
		binaryPath, err = extractTarGz(resp.Body, tmpDir)
	}
	if err != nil {
		return fmt.Errorf("extract: %w", err)
	}

	// Verify it's an executable
	info, err := os.Stat(binaryPath)
	if err != nil {
		return fmt.Errorf("stat extracted binary: %w", err)
	}
	if info.Size() == 0 {
		return fmt.Errorf("extracted binary is empty")
	}

	// Verify it's actually an executable
	if info.Mode()&0o111 == 0 {
		if err := os.Chmod(binaryPath, 0o755); err != nil {
			return fmt.Errorf("chmod binary: %w", err)
		}
	}

	fmt.Fprintf(os.Stderr, "  Installing to %s...\n", execPath)

	// Rename original as backup (cross-device safe)
	backupPath := execPath + ".bak"
	os.Rename(execPath, backupPath) // best-effort

	// Copy new binary in place
	if err := copyFile(binaryPath, execPath); err != nil {
		// Restore backup
		os.Rename(backupPath, execPath)
		return fmt.Errorf("install binary: %w", err)
	}

	// Make executable
	os.Chmod(execPath, 0o755)

	// Remove backup on success
	os.Remove(backupPath)

	fmt.Fprintf(os.Stderr, "  ✓  Updated to %s\n", m.release.TagName)
	return nil
}

// ── Extraction ────────────────────────────────────────────────

func extractTarGz(r io.Reader, destDir string) (string, error) {
	gr, err := gzip.NewReader(r)
	if err != nil {
		return "", fmt.Errorf("gzip: %w", err)
	}
	defer gr.Close()

	tr := tar.NewReader(gr)
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return "", fmt.Errorf("tar: %w", err)
		}

		if hdr.FileInfo().IsDir() {
			continue
		}

		name := filepath.Base(hdr.Name)
		if name == "" || name == "." || name == ".." {
			continue
		}

		// Accept any binary named yvid or yvid.exe
		if !isBinaryName(name) {
			continue
		}

		outPath := filepath.Join(destDir, name)
		out, err := os.OpenFile(outPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, hdr.FileInfo().Mode())
		if err != nil {
			return "", fmt.Errorf("create extracted file: %w", err)
		}
		defer out.Close()

		if _, err := io.Copy(out, tr); err != nil {
			return "", fmt.Errorf("write extracted file: %w", err)
		}

		return outPath, nil
	}

	return "", fmt.Errorf("no binary found in archive")
}

func extractZip(r io.Reader, destDir string) (string, error) {
	// Read all data into buffer for zip reader
	data, err := io.ReadAll(r)
	if err != nil {
		return "", fmt.Errorf("read zip: %w", err)
	}

	// Parse zip from bytes
	zr, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return "", fmt.Errorf("zip reader: %w", err)
	}

	for _, f := range zr.File {
		if f.FileInfo().IsDir() {
			continue
		}
		name := filepath.Base(f.Name)
		if !isBinaryName(name) {
			continue
		}

		rc, err := f.Open()
		if err != nil {
			return "", fmt.Errorf("open zip entry: %w", err)
		}
		defer rc.Close()

		outPath := filepath.Join(destDir, name)
		out, err := os.OpenFile(outPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o755)
		if err != nil {
			return "", fmt.Errorf("create extracted file: %w", err)
		}
		defer out.Close()

		if _, err := io.Copy(out, rc); err != nil {
			return "", fmt.Errorf("write extracted file: %w", err)
		}

		return outPath, nil
	}

	return "", fmt.Errorf("no binary found in zip archive")
}

// ── Helpers ───────────────────────────────────────────────────

func (m *Manager) assetSuffix() string {
	osName := runtime.GOOS
	arch := goArch()
	return fmt.Sprintf("_%s_%s", osName, arch)
}

func goArch() string {
	switch runtime.GOARCH {
	case "amd64":
		return "amd64"
	case "arm64":
		return "arm64"
	default:
		return runtime.GOARCH
	}
}

func isBinaryName(name string) bool {
	base := strings.TrimSuffix(name, ".exe")
	return base == "yvid"
}

func listAssetNames(assets []Asset) string {
	var names []string
	for _, a := range assets {
		names = append(names, a.Name)
	}
	return strings.Join(names, ", ")
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

// SHA256Sum computes the SHA-256 checksum of a file.
func SHA256Sum(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
