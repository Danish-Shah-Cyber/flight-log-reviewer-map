# Desktop App

Local Electron version of Flight Log Reviewer Pro.

## Target Shape

- Electron desktop shell.
- Same React review UI as the web app.
- Local Python service for parsing and review artifacts.
- Shared `packages/reviewer-core` parser and analysis engine.

## Desktop-Specific Requirements

- Open local `.ulg`, `.bin`, `.log`, and `.tlog` files without uploading them.
- Avoid hosted request timeouts for very large logs.
- Keep raw logs private by default.
- Store review artifacts in a user-selected local workspace.
- Package a Windows installer after the MVP is stable.
