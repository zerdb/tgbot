# GigaAM Observer browser extension

This extension sends only open-tab metadata (HTTP/HTTPS URL, title, active flag, browser/window identifiers) to the local receiver at `127.0.0.1:8765`. It does not inspect page DOM, page text, form fields, passwords, cookies, or browsing history.

## Install in Chromium browsers (Chrome, Edge, Opera)
1. Start GigaAM Assistant with Observer enabled and Browser category enabled.
2. Open the browser's extensions page.
3. Enable Developer mode.
4. Choose "Load unpacked" and select this folder.
5. Keep the extension enabled. It reports a snapshot on tab changes and every minute.

Firefox support requires loading this folder as a temporary add-on from `about:debugging#/runtime/this-firefox`; Firefox may require a Firefox-compatible manifest/background configuration and may not support the Chromium service-worker implementation. Use the separate Firefox instructions when provided in a future release.

The receiver binds only to IPv4 loopback (127.0.0.1). Tab metadata can contain sensitive URLs; it remains in the local Observer database.
