package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/BurntSushi/toml"
	"github.com/adrg/xdg"
)

const (
	appName     = "yvid"
	configFile  = "config.toml"
	defaultPerm = 0o755
)

// Config represents the persistent configuration for yvid.
type Config struct {
	// General
	OutputDir          string   `toml:"output-dir"`
	Format             string   `toml:"default-format"`
	Quality            string   `toml:"default-quality"`
	Subtitles          bool     `toml:"default-subs"`
	AutoUpdate         bool     `toml:"auto-update"`
	DownloadArchive    bool     `toml:"download-archive"`
	ResumePrompt       bool     `toml:"resume-prompt"`
	CookiesFile        string   `toml:"cookies-file"`
	CookiesFromBrowser string   `toml:"cookies-from-browser"`
	FavoriteDirs       []string `toml:"favorite-dirs"`

	// paths (internal, not serialized)
	configPath string
}

// Default returns a Config with sensible defaults.
func Default() *Config {
	return &Config{
		OutputDir:       filepath.Join(xdg.UserDirs.Download, "YVid"),
		Format:          "mp4",
		Quality:         "1080p",
		Subtitles:       false,
		AutoUpdate:      true,
		DownloadArchive: true,
		ResumePrompt:    true,
		FavoriteDirs:    []string{"~/Downloads", "~/Videos", "~/Music"},
	}
}

// Load reads config from the XDG config path.
// If file doesn't exist, returns defaults without error.
func Load() (*Config, error) {
	path, err := configFilePath()
	if err != nil {
		return Default(), nil
	}

	cfg := Default()
	cfg.configPath = path

	if _, err := os.Stat(path); os.IsNotExist(err) {
		return cfg, nil
	}

	_, err = toml.DecodeFile(path, cfg)
	if err != nil {
		return Default(), fmt.Errorf("parse config: %w", err)
	}

	return cfg, nil
}

// Save writes config to disk, creating parent directories.
func (c *Config) Save() error {
	path, err := configFilePath()
	if err != nil {
		return err
	}
	c.configPath = path

	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, defaultPerm); err != nil {
		return fmt.Errorf("create config dir: %w", err)
	}

	f, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("create config file: %w", err)
	}
	defer f.Close()

	return toml.NewEncoder(f).Encode(c)
}

// Path returns the config file path.
func (c *Config) Path() string {
	return c.configPath
}

// Render returns the config as a human-readable string.
func (c *Config) Render() string {
	var b strings.Builder
	b.WriteString("# yvid configuration\n")
	b.WriteString(fmt.Sprintf("config-file         = %s\n", c.configPath))
	b.WriteString(fmt.Sprintf("output-dir          = %s\n", c.OutputDir))
	b.WriteString(fmt.Sprintf("default-format      = %s\n", c.Format))
	b.WriteString(fmt.Sprintf("default-quality     = %s\n", c.Quality))
	b.WriteString(fmt.Sprintf("default-subs        = %v\n", c.Subtitles))
	b.WriteString(fmt.Sprintf("auto-update         = %v\n", c.AutoUpdate))
	b.WriteString(fmt.Sprintf("download-archive    = %v\n", c.DownloadArchive))
	b.WriteString(fmt.Sprintf("resume-prompt       = %v\n", c.ResumePrompt))
	if c.CookiesFile != "" {
		b.WriteString(fmt.Sprintf("cookies-file        = %s\n", c.CookiesFile))
	}
	if c.CookiesFromBrowser != "" {
		b.WriteString(fmt.Sprintf("cookies-from-browser = %s\n", c.CookiesFromBrowser))
	}
	if len(c.FavoriteDirs) > 0 {
		b.WriteString(fmt.Sprintf("favorite-dirs = %s\n", strings.Join(c.FavoriteDirs, ", ")))
	}
	return b.String()
}

// Set updates a config value by key.
func (c *Config) Set(key, value string) error {
	switch key {
	case "output-dir":
		c.OutputDir = value
	case "default-format":
		if value != "mp4" && value != "mp3" {
			return fmt.Errorf("invalid format %q, expected mp4 or mp3", value)
		}
		c.Format = value
	case "default-quality":
		valid := map[string]bool{"best": true, "2160p": true, "1080p": true, "720p": true, "480p": true}
		if !valid[value] {
			return fmt.Errorf("invalid quality %q, expected best/2160p/1080p/720p/480p", value)
		}
		c.Quality = value
	case "default-subs":
		c.Subtitles = truthy(value)
	case "auto-update":
		c.AutoUpdate = truthy(value)
	case "download-archive":
		c.DownloadArchive = truthy(value)
	case "resume-prompt":
		c.ResumePrompt = truthy(value)
	case "cookies-file":
		c.CookiesFile = value
	case "cookies-from-browser":
		c.CookiesFromBrowser = value
	case "favorite-dirs":
		c.FavoriteDirs = strings.Split(value, ",")
	default:
		return fmt.Errorf("unknown config key: %s", key)
	}
	return nil
}

// ArchivePath returns the path to the download archive file.
func (c *Config) ArchivePath() string {
	dir, err := ConfigDir()
	if err != nil {
		return ""
	}
	return filepath.Join(dir, "archive.txt")
}

func truthy(value string) bool {
	return value == "true" || value == "yes" || value == "1"
}

func configFilePath() (string, error) {
	return xdg.ConfigFile(filepath.Join(appName, configFile))
}

// ConfigDir returns the XDG config directory for yvid.
func ConfigDir() (string, error) {
	return xdg.ConfigFile(appName)
}

// CacheDir returns the XDG cache directory for yvid.
func CacheDir() (string, error) {
	return xdg.CacheFile(appName)
}
