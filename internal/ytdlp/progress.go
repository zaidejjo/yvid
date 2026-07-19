package ytdlp

import (
	"encoding/json"
	"strconv"
	"strings"
)

// progressJSON matches the --progress-template JSON output.
type progressJSON struct {
	Status     string `json:"status"`
	Percent    string `json:"percent"`
	Speed      string `json:"speed"`
	ETA        string `json:"eta"`
	Downloaded string `json:"downloaded"`
	Total      string `json:"total"`
}

// parseProgressLine attempts to parse a JSON progress line from yt-dlp.
func parseProgressLine(line string) ProgressEvent {
	// Try JSON first
	var pj progressJSON
	if err := json.Unmarshal([]byte(line), &pj); err == nil && pj.Status != "" {
		return progressFromJSON(pj)
	}

	// Check for completion message
	if strings.Contains(line, "has already been downloaded") {
		return ProgressEvent{Status: "error", Message: "already downloaded"}
	}
	if strings.Contains(line, "ERROR:") {
		return ProgressEvent{Status: "error", Message: extractErrorMessage(line)}
	}
	if strings.Contains(line, "[download] 100%") {
		return ProgressEvent{Status: "completed"}
	}
	if strings.Contains(line, "[ExtractAudio]") || strings.Contains(line, "[ffmpeg]") {
		return ProgressEvent{Status: "post_processing"}
	}

	return ProgressEvent{Status: "unknown"}
}

func progressFromJSON(pj progressJSON) ProgressEvent {
	evt := ProgressEvent{Status: pj.Status}

	if pj.Percent != "" && pj.Percent != "N/A" {
		v, err := strconv.ParseFloat(strings.TrimSuffix(pj.Percent, "%"), 64)
		if err == nil {
			evt.Percent = v
		}
	}

	if pj.Speed != "" && pj.Speed != "N/A" {
		v, err := strconv.ParseFloat(pj.Speed, 64)
		if err == nil {
			evt.Speed = v
		}
	}

	if pj.ETA != "" && pj.ETA != "N/A" {
		v, err := strconv.ParseFloat(pj.ETA, 64)
		if err == nil {
			evt.ETA = v
		}
	}

	if pj.Downloaded != "" && pj.Downloaded != "N/A" {
		v, err := strconv.ParseInt(pj.Downloaded, 10, 64)
		if err == nil {
			evt.Downloaded = v
		}
	}

	if pj.Total != "" && pj.Total != "N/A" {
		v, err := strconv.ParseInt(pj.Total, 10, 64)
		if err == nil {
			evt.Total = v
		}
	}

	return evt
}

func extractErrorMessage(line string) string {
	// "ERROR: something went wrong"
	idx := strings.Index(line, "ERROR:")
	if idx >= 0 {
		return strings.TrimSpace(line[idx+6:])
	}
	return line
}
