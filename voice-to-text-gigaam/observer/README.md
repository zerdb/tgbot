# GigaAM Observer

GigaAM Observer is a local activity-awareness subsystem for the Windows voice assistant.

## Automatic collection

Observer starts with the assistant. No category permissions or general enable switch are shown in settings; the user has approved these metadata categories:

- **Files and folders:** records created, modified and deleted file metadata (name, path and timestamps) in configured user folders. It does not read file contents.
- **Programs:** records application/process starts and exits with process name, PID and executable path. Common Windows infrastructure processes are excluded.
- **Active window and focus duration:** records foreground application, window title and how long it remained active.
- **Repeated-work scenarios:** local analysis can identify recurring application launches and combinations/sequences where event history provides enough evidence. Suggestions are stored locally for review and acceptance/dismissal.

The assistant does not record keystrokes, screen contents, microphone audio, document contents, browser tabs, page contents, cookies or passwords.

## Clipboard — optional

The only permission checkbox is “Собирать текст буфера обмена”. It is off by default. When enabled, changed plain-text clipboard content is polled and stored locally only if it passes conservative secret-pattern checks. Likely passwords, access tokens, API keys, email addresses and oversized text are discarded. This is best-effort filtering, not a guarantee; clipboard history must not be treated as a secure vault. Uncheck the option to stop clipboard collection.

## Local storage

%LOCALAPPDATA%\GigaAMVoiceAssistant\observer\

- config.json — settings;
- observer.sqlite3 — event history, notes and suggestions.

History has no automatic expiration. The history window supports filtering and CSV export. The database remains on this computer. No raw event database is uploaded.

## Insights and internet AI

The “Анализ привычек” action runs deterministic local analysis over recent event history and stores explainable suggestions that can be accepted or dismissed. It does not call an internet service.

An optional OpenAI-compatible adapter exists for future use. It is disabled by default and does not read the database or upload events automatically. Any future call must receive a minimized, user-approved summary only.

## Limitations

- File monitoring watches configured user folders; it is not a whole-disk index.
- Process and focus monitoring are polling-based, so very short-lived events can be missed.
- Printing and USB collectors are not implemented.
- Browser monitoring is deliberately excluded.
- Clipboard secret filtering is heuristic and cannot guarantee that every secret is detected.
