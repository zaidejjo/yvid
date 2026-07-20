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
	// App styling — clean, no outer border, no background fill
	AppStyle = lipgloss.NewStyle().
			Padding(1, 2)

	TitleStyle = lipgloss.NewStyle().
			Foreground(accent).
			Bold(true).
			MarginBottom(1)

	// Input field — width handled by textinput.Model.Width, style just adds border/padding
	InputStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(border).
			Padding(0, 1)

	FocusedInputStyle = InputStyle.
				BorderForeground(accent)

	// Search results — no fixed width, adapts to terminal
	ResultItemStyle = lipgloss.NewStyle().
			Padding(0, 1)

	ResultSelectedStyle = ResultItemStyle.
				Foreground(accent).
				Background(bgLight).
				Bold(true)

	// Progress
	ProgressBarStyle = lipgloss.NewStyle().
				Padding(0, 1)

	ProgressPercentStyle = lipgloss.NewStyle().
				Foreground(accent).
				Bold(true).
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

	WarningStyle = lipgloss.NewStyle().
			Foreground(warning).
			Bold(true)

	SpinnerStyle = lipgloss.NewStyle().
			Foreground(accent)

	// Status bar
	StatusBarStyle = lipgloss.NewStyle().
			Background(bgLight).
			Padding(0, 1)

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

// Card styles for list selection screens (media type, quality, dir picker)
var (
	cardBase = lipgloss.NewStyle().
			Padding(0, 2)

	cardSelected = cardBase.
			Foreground(accent).
			Background(bgLight).
			Bold(true)

	cardNormal = cardBase.
			Foreground(text)
)
