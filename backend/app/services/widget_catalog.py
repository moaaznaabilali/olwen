"""The set of dashboard widgets users can enable/disable.

Source of truth for the prefs UI. Each entry tells the frontend whether the
widget is currently live or a placeholder ("soon"). Order here = the order
they're rendered in the dashboard columns.
"""

WIDGETS = [
    # Core widgets — already wired and rendering real data.
    {"key": "tasks",    "name": "Tasks",       "column": "left",  "live": True,
     "description": "Your task lists, with one-tap suggestions and cinematic review.",
     "glyph": "✓", "color": "#5EEAD4", "core": True},

    {"key": "github",   "name": "GitHub",      "column": "left",  "live": True,
     "description": "Real push, PR, and issue activity from your account.",
     "glyph": "⌗", "color": "#A78BFA", "core": False},

    {"key": "inbox",    "name": "Inbox",       "column": "right", "live": True,
     "description": "Olwen triages your email and reads the important ones.",
     "glyph": "✉", "color": "#67E8F9", "core": False},

    {"key": "calendar", "name": "Today",       "column": "right", "live": True,
     "description": "Upcoming events from your connected Google calendar.",
     "glyph": "▦", "color": "#FBBF24", "core": False},

    {"key": "news",     "name": "News",        "column": "right", "live": True,
     "description": "Curated by the topics you follow — AI, tech, finance, world.",
     "glyph": "✦", "color": "#22D3EE", "core": False},

    # Placeholders — visible in the catalog, status='soon' so we can ship later.
    {"key": "weather",  "name": "Weather",     "column": "left",  "live": False,
     "description": "Local weather, sunrise/sunset, and air quality.",
     "glyph": "☁", "color": "#67E8F9", "core": False},

    {"key": "focus",    "name": "Focus timer", "column": "left",  "live": False,
     "description": "A quiet pomodoro timer Olwen guards for you.",
     "glyph": "◴", "color": "#F472B6", "core": False},

    {"key": "notes",    "name": "Quick notes", "column": "left",  "live": False,
     "description": "Scratch notes that sync to Olwen's memory.",
     "glyph": "✎", "color": "#A7F3D0", "core": False},

    {"key": "health",   "name": "Health",      "column": "right", "live": True,
     "description": "Real activities from Strava — runs, rides, swims, training load.",
     "glyph": "♥", "color": "#F472B6", "core": False},

    {"key": "markets",  "name": "Markets",     "column": "right", "live": False,
     "description": "A small ticker of stocks and crypto you follow.",
     "glyph": "$", "color": "#FB923C", "core": False},
]

# default — what new users see before they pick anything
DEFAULT_KEYS = ["tasks", "github", "inbox", "calendar", "news"]


def default_for_user() -> list[str]:
    return list(DEFAULT_KEYS)
