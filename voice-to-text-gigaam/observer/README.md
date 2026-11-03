# GigaAM Observer

GigaAM Observer is an opt-in, local activity-awareness subsystem for the Windows voice assistant.

## Current status

The main assistant window includes Observer settings, a local event-history window with category filtering, manual notes and CSV export, plus a local insights window. The insights engine detects repeated application launches, recurring daily applications and busy folders, then stores explainable suggestions for user review and acceptance/dismissal. Monitoring stays off by default; the user must explicitly enable it, choose file and/or app monitoring, and confirm consent. Saving settings applies the selected collectors immediately; disabling Observer stops them. Only file and process categories are currently implemented.

This first milestone contains only the storage and configuration foundation:
- SQLite event history and indexes;
- provider-agnostic internet AI adapter for OpenAI-compatible APIs;
- separate JSON configuration with safe defaults;
- an Observer lifecycle manager;
- opt-in file metadata monitoring for selected folders (Desktop, Documents, Pictures, Downloads);\n- opt-in process start/stop monitoring (process name, PID and executable path only);

Observer is **disabled by default**. Creating its database does not mean monitoring is enabled. Event collection starts only after explicit opt-in and category selection.

## Data location

`%LOCALAPPDATA%\GigaAMVoiceAssistant\observer\`
- `config.json` — preferences;
- `observer.sqlite3` — event history, notes, and suggestions.

The file collector takes an initial baseline and then polls every 10 seconds for created, modified and deleted files. The process collector takes an initial baseline and polls every 3 seconds for process starts and exits; very short-lived processes may be missed. It does not read file contents. Existing files are not imported into history. Only folders resolved from Windows known-folder locations are proposed by default; no whole-drive scan is performed. File monitoring remains off unless both Observer and the `files` category are explicitly enabled in config. Process monitoring remains off unless both Observer and the `apps` category are explicitly enabled.

History has no automatic expiration. The history window can export the selected view to CSV. Manual event deletion is not yet exposed in the UI; the database remains local.

## Planned milestones

1. Storage, configuration, and lifecycle foundation (current).
2. File collector for the four selected user folders and process lifecycle collector (implemented).
3. USB and print event collectors.
4. Daily repetition analysis and suggestion engine.
5. Observer history window, tray integration, and richer folder/exclusion controls (settings dialog started).
6. Optional internet AI adapter for explaining detected patterns and drafting suggestions.
7. Windows startup integration and final acceptance checks.

## Internet AI brain

`ai_client.py` supports OpenAI-compatible chat-completions endpoints without a provider SDK. Configure `ai.enabled`, `ai.base_url`, and `ai.model` in `config.json`. If the provider requires a key, place it in the environment variable named by `ai.api_key_env` (default: `GIGAAM_OBSERVER_API_KEY`). The key is never stored in the config or database. The caller must explicitly pass a minimized summary to `explain_summary()`; the adapter does not read the event database or upload events on its own. This lets a free hosted model be used now and a paid API later by changing configuration.

## Privacy

- No browser tracking is included in the agreed scope.
- No keystroke logging, clipboard capture, screen recording, or microphone surveillance.
- No document contents are collected by default.\n- Process monitoring does not collect command lines, window titles, keystrokes, or process memory.
- Collectors will be individually configurable and visibly indicated.
- The database remains local. Any future AI request will send only a minimized, user-approved summary, never the raw event database.


## Local insights

The "Анализ привычек" window runs deterministic analysis over the latest seven days of stored metadata. It can identify repeated application starts, applications seen across multiple days, and folders with repeated file changes. Each suggestion includes its evidence count/context, is deduplicated, and can be accepted or dismissed. The analysis does not call an internet AI service and does not inspect document contents. The user starts analysis manually; there is no automatic daily job yet.
