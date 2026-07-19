package cli

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/zaidejjo/yvid/internal/upgrade"
)

func newUpgradeCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "upgrade",
		Short: "Self-upgrade yvid to latest version",
		Long: `Check GitHub Releases for the latest yvid binary.

Downloads, verifies, and replaces the current binary automatically.
Uses GitHub API to find the latest release for your OS/arch.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			force, _ := cmd.Flags().GetBool("force")

			fmt.Fprintln(os.Stderr, "  Checking for updates...")

			mgr := upgrade.NewManager(
				"github.com/zaidejjo/yvid",
				version,
			)

			released, newVer, err := mgr.Check()
			if err != nil {
				return fmt.Errorf("update check failed: %w", err)
			}

			if !released {
				fmt.Fprintf(os.Stderr, "  ✓  Already up-to-date (%s)\n", version)
				return nil
			}

			if !force {
				fmt.Fprintf(os.Stderr, "  New version available: %s → %s\n", version, newVer)
				fmt.Fprintf(os.Stderr, "  Run 'yvid upgrade --force' to install\n")
				return nil
			}

			if err := mgr.Upgrade(); err != nil {
				return fmt.Errorf("upgrade failed: %w", err)
			}

			fmt.Fprintf(os.Stderr, "  ✓  Upgraded to %s\n", newVer)
			return nil
		},
	}

	cmd.Flags().BoolP("force", "f", false, "download and install the latest version")
	return cmd
}
