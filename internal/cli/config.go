package cli

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/zaidejjo/yvid/internal/config"
	"github.com/zaidejjo/yvid/internal/download"
)

func newConfigCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "config",
		Short: "Manage yvid configuration",
		Long: `View or modify persistent configuration.

Configuration file location: ~/.config/yvid/config.toml

Subcommands:
  yvid config init     Create default config file
  yvid config show     Display current configuration
  yvid config set      Set a configuration value`,
	}

	cmd.AddCommand(
		&cobra.Command{
			Use:   "init",
			Short: "Create default config file",
			RunE: func(cmd *cobra.Command, args []string) error {
				cfg, err := config.Load()
				if err != nil {
					return fmt.Errorf("cannot load config: %w", err)
				}
				if err := cfg.Save(); err != nil {
					return fmt.Errorf("cannot save config: %w", err)
				}
				fmt.Fprintf(os.Stderr, "Config created at: %s\n", cfg.Path())
				return nil
			},
		},
		&cobra.Command{
			Use:   "show",
			Short: "Display current configuration",
			RunE: func(cmd *cobra.Command, args []string) error {
				cfg, err := config.Load()
				if err != nil {
					return fmt.Errorf("cannot load config: %w", err)
				}
				fmt.Println(cfg.Render())

				// Archive info
				if cfg.DownloadArchive {
					archivePath := cfg.ArchivePath()
					archive, err := download.NewArchive(archivePath)
					if err == nil {
						fmt.Fprintf(os.Stderr, "download-archive = %s\n", archivePath)
						fmt.Fprintf(os.Stderr, "archive-entries  = %d\n", archive.Count())
					}
				}

				// Part file check
				if cfg.OutputDir != "" {
					parts, err := download.ScanPartFiles(cfg.OutputDir)
					if err == nil && len(parts) > 0 {
						fmt.Fprintf(os.Stderr, "\n! %s\n", download.PartFileInfo(parts))
					}
				}

				return nil
			},
		},
		&cobra.Command{
			Use:   "set <key> <value>",
			Short: "Set a config value (e.g. output-dir, default-format)",
			Args:  cobra.ExactArgs(2),
			RunE: func(cmd *cobra.Command, args []string) error {
				cfg, err := config.Load()
				if err != nil {
					return fmt.Errorf("cannot load config: %w", err)
				}
				if err := cfg.Set(args[0], args[1]); err != nil {
					return fmt.Errorf("cannot set config: %w", err)
				}
				if err := cfg.Save(); err != nil {
					return fmt.Errorf("cannot save config: %w", err)
				}
				fmt.Fprintf(os.Stderr, "  ✓  %s = %s\n", args[0], args[1])
				return nil
			},
		},
	)

	return cmd
}
