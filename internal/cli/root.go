package cli

import (
	"context"
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/zaidejjo/yvid/internal/tui"
	"github.com/zaidejjo/yvid/internal/ytdlp"
)

var (
	version = "1.2.0"
	commit  = "dev"
	date    = "unknown"

	cfgFile string
)

// NewRootCmd creates the root cobra command for yvid.
func NewRootCmd() *cobra.Command {
	root := &cobra.Command{
		Use:   "yvid",
		Short: "Modern Video Downloader — fast, interactive, cross-platform",
		Long: `YVid is a blazing-fast video/audio downloader wrapping yt-dlp.
Download from YouTube, Vimeo, Twitch, and 1000+ sites.
Features interactive TUI, format selection, audio extraction, trimming, and more.`,
		Version: fmt.Sprintf("%s (commit: %s, built: %s)", version, commit, date),
		RunE: func(cmd *cobra.Command, args []string) error {
			url, _ := cmd.Flags().GetString("url")
			format, _ := cmd.Flags().GetString("format")
			quality, _ := cmd.Flags().GetString("quality")
			output, _ := cmd.Flags().GetString("output")
			subs, _ := cmd.Flags().GetBool("subs")
			trimStart, _ := cmd.Flags().GetString("trim-start")
			trimEnd, _ := cmd.Flags().GetString("trim-end")

			target := url
			if target == "" && len(args) > 0 {
				target = args[0]
			}

			// No args → interactive TUI
			if target == "" {
				return runTUI(cmd, "")
			}

			// Hybrid: url provided but not all options → TUI with pre-filled URL
			if format == "" || quality == "" {
				return runTUI(cmd, target)
			}

			// Direct: all flags provided → download immediately
			return runDirect(cmd, target, format, quality, output, subs, trimStart, trimEnd)
		},
	}

	root.PersistentFlags().StringVarP(&cfgFile, "config", "c", "", "config file (default ~/.config/yvid/config.toml)")

	root.Flags().StringP("url", "u", "", "video URL or search query")
	root.Flags().StringP("format", "f", "", "output format (mp4, mp3)")
	root.Flags().StringP("quality", "q", "", "video quality (best, 2160p, 1080p, 720p, 480p)")
	root.Flags().StringP("output", "o", "", "output directory")
	root.Flags().BoolP("subs", "s", false, "embed subtitles when available")
	root.Flags().String("trim-start", "", "trim start time (HH:MM:SS)")
	root.Flags().String("trim-end", "", "trim end time (HH:MM:SS)")

	root.AddCommand(newConfigCmd())
	root.AddCommand(newUpgradeCmd())
	root.AddCommand(newDownloadCmd())

	return root
}

func runTUI(cmd *cobra.Command, url string) error {
	ctx := context.Background()
	return tui.Run(ctx, url)
}

func runDirect(cmd *cobra.Command, url, format, quality, output string, subs bool, trimStart, trimEnd string) error {
	opts := ytdlp.Options{
		URL:       url,
		Format:    format,
		Quality:   quality,
		Output:    output,
		Subtitles: subs,
		TrimStart: trimStart,
		TrimEnd:   trimEnd,
	}

	dl := ytdlp.NewDownloader()
	progress, err := dl.Download(cmd.Context(), opts)
	if err != nil {
		return fmt.Errorf("download failed: %w", err)
	}

	for p := range progress {
		switch p.Status {
		case "downloading":
			fmt.Fprintf(os.Stderr, "\r  %s  %.1f%%  %s/s  ETA: %s        ",
				p.PercentBar(), p.Percent, p.SpeedHuman(), p.ETAHuman())
		case "post_processing":
			fmt.Fprintln(os.Stderr, "\n  ⏳  Post-processing...")
		case "completed":
			fmt.Fprintln(os.Stderr, "\n  ✓  Download complete")
		case "error":
			fmt.Fprintf(os.Stderr, "\n  ✘  %s\n", p.Message)
		}
	}
	return nil
}
