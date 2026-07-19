package tui

import (
	"github.com/charmbracelet/lipgloss"
)

// Color palette matching YVid brand
var (
	accent   = lipgloss.Color("#007AFF")
	success  = lipgloss.Color("#34C759")
	warning  = lipgloss.Color("#FF9F0A")
	errColor = lipgloss.Color("#FF453A")
	text     = lipgloss.Color("#FFFFFF")
	dimText  = lipgloss.Color("#8E8E93")
	bgDark   = lipgloss.Color("#1C1C1E")
	bgLight  = lipgloss.Color("#2C2C2E")
	border   = lipgloss.Color("#38383A")
)

// Styles
var (
	// App styling
	AppStyle = lipgloss.NewStyle().
			Padding(1, 2).
			Border(lipgloss.RoundedBorder()).
			BorderForeground(border).
			Background(bgDark)

	TitleStyle = lipgloss.NewStyle().
			Foreground(accent).
			Bold(true).
			MarginBottom(1)

	// Input field
	InputStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(border).
			Padding(0, 1).
			Width(60)

	FocusedInputStyle = InputStyle.Copy().
				BorderForeground(accent)

	// Search results
	ResultItemStyle = lipgloss.NewStyle().
			Padding(0, 1).
			Width(70)

	ResultSelectedStyle = ResultItemStyle.Copy().
				Foreground(accent).
				Background(bgLight).
				Bold(true)

	// Progress
	ProgressBarStyle = lipgloss.NewStyle().
				Width(50).
				Padding(0, 1)

	ProgressPercentStyle = lipgloss.NewStyle().
				Foreground(accent).
				Bold(true).
				Width(7).
				Align(lipgloss.Right)

	// Labels
	LabelStyle = lipgloss.NewStyle().
			Foreground(dimText).
			MarginRight(1)

	ValueStyle = lipgloss.NewStyle().
			Foreground(text)

	SuccessStyle = lipgloss.NewStyle().
			Foreground(success).
			Bold(true)

	ErrorStyle = lipgloss.NewStyle().
			Foreground(errColor).
			Bold(true)

	SpinnerStyle = lipgloss.NewStyle().
			Foreground(accent)

	// Status bar
	StatusBarStyle = lipgloss.NewStyle().
			Background(bgLight).
			Padding(0, 1).
			Width(70)

	// Help text
	HelpStyle = lipgloss.NewStyle().
			Foreground(dimText).
			Italic(true).
			MarginTop(1)

	// Separator
	Separator = lipgloss.NewStyle().
			Foreground(border).
			Render("────────────────────────────────────────────")
)
