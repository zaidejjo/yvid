package cli

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/zaidejjo/yvid/internal/ytdlp"
)

func newDownloadCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "download [url]",
		Short: "Download video or audio directly",
		Long: `Download a video/audio from a URL.

Provides real-time progress via yt-dlp subprocess.
Supports format selection, quality, subtitles, and trimming.`,
		Args: cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			url, _ := cmd.Flags().GetString("url")
			format, _ := cmd.Flags().GetString("format")
			quality, _ := cmd.Flags().GetString("quality")
			output, _ := cmd.Flags().GetString("output")
			subs, _ := cmd.Flags().GetBool("subs")

			if url == "" && len(args) == 1 {
				url = args[0]
			}
			if url == "" {
				return fmt.Errorf("url is required")
			}

			opts := ytdlp.Options{
				URL:       url,
				Format:    format,
				Quality:   quality,
				Output:    output,
				Subtitles: subs,
			}

			dl := ytdlp.NewDownloader()
			progress, err := dl.Download(cmd.Context(), opts)
			if err != nil {
				return fmt.Errorf("download failed: %w", err)
			}

			for p := range progress {
				if p.Status == "downloading" {
					fmt.Fprintf(os.Stderr, "\r  %s  %.1f%%  %s/s  ETA: %s",
						p.PercentBar(), p.Percent, p.SpeedHuman(), p.ETAHuman())
				} else if p.Status == "completed" {
					fmt.Fprintf(os.Stderr, "\n  ✓  Downloaded: %s\n", p.OutputPath)
				} else if p.Status == "error" {
					fmt.Fprintf(os.Stderr, "\n  ✘  %s\n", p.Message)
				}
			}
			return nil
		},
	}

	cmd.Flags().StringP("url", "u", "", "video URL")
	cmd.Flags().StringP("format", "f", "", "output format (mp4, mp3)")
	cmd.Flags().StringP("quality", "q", "", "video quality (best, 2160p, 1080p, 720p, 480p)")
	cmd.Flags().StringP("output", "o", "", "output directory")
	cmd.Flags().BoolP("subs", "s", false, "embed subtitles when available")

	return cmd
}
