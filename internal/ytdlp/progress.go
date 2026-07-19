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
	// yt-dlp --progress-template "json:..." outputs lines like:
	//   json:{"status":"downloading","percent":"45.2",...}
	// Strip the "json:" prefix if present.
	raw := line
	if strings.HasPrefix(raw, "json:") {
		raw = raw[5:]
	}

	// Try JSON
	var pj progressJSON
	if err := json.Unmarshal([]byte(raw), &pj); err == nil && pj.Status != "" {
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
	evt := ProgressEvent{
		Status: pj.Status,
	}

	if v := parseNAFloat(pj.Percent); v >= 0 {
		evt.Percent = v
	}

	if v := parseNAFloat(pj.Speed); v >= 0 {
		evt.Speed = v
	}

	if v := parseNAFloat(pj.ETA); v >= 0 {
		evt.ETA = v
	}

	if v := parseNAInt(pj.Downloaded); v >= 0 {
		evt.Downloaded = v
	}

	if v := parseNAInt(pj.Total); v >= 0 {
		evt.Total = v
	}

	return evt
}

// parseNAFloat parses a float from a yt-dlp field that may be "NA".
// Returns -1 if the value is NA or unparseable.
func parseNAFloat(s string) float64 {
	s = strings.TrimSpace(s)
	if s == "" || s == "NA" || s == "N/A" || s == "n/a" {
		return -1
	}
	s = strings.TrimSuffix(s, "%")
	v, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return -1
	}
	return v
}

// parseNAInt parses an int from a yt-dlp field that may be "NA".
// Returns -1 if the value is NA or unparseable.
func parseNAInt(s string) int64 {
	s = strings.TrimSpace(s)
	if s == "" || s == "NA" || s == "N/A" || s == "n/a" {
		return -1
	}
	v, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return -1
	}
	return v
}

func extractErrorMessage(line string) string {
	idx := strings.Index(line, "ERROR:")
	if idx >= 0 {
		return strings.TrimSpace(line[idx+6:])
	}
	return line
}
