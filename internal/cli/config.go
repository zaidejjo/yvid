package cli

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/zaidejjo/yvid/internal/config"
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
