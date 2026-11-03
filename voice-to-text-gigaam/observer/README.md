# GigaAM Observer

GigaAM Observer is an opt-in, local activity-awareness subsystem for the Windows voice assistant.

## Current status

This first milestone contains only the storage and configuration foundation:
- SQLite event history and indexes;
- separate JSON configuration with safe defaults;
- an Observer lifecycle manager;
- no file, process, print, USB, browser, keyboard, or screen monitoring yet.

Observer is **disabled by default**. Creating its database does not mean monitoring is enabled. Event collection starts only after explicit opt-in and category selection.

## Data location

`%LOCALAPPDATA%\GigaAMVoiceAssistant\observer\`
- `config.json` — preferences;
- `observer.sqlite3` — event history, notes, and suggestions.

History has no automatic expiration. Users will have manual export and deletion controls in a later UI milestone.

## Planned milestones

1. Storage, configuration, and lifecycle foundation (current).
2. File and application event collectors.
3. USB and print event collectors.
4. Daily repetition analysis and suggestion engine.
5. Observer settings/history window and tray integration.
6. Optional internet AI adapter for explaining detected patterns and drafting suggestions.
7. Windows startup integration and final acceptance checks.

## Privacy

- No browser tracking is included in the agreed scope.
- No keystroke logging, clipboard capture, screen recording, or microphone surveillance.
- No document contents are collected by default.
- Collectors will be individually configurable and visibly indicated.
- The database remains local. Any future AI request will send only a minimized, user-approved summary, never the raw event database.
