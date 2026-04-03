# Server Config Examples

- `app.env.example` - default local development profile.
- `test.env.example` - test-oriented profile.
- `prod.env.example` - production-safe profile template.

Environment variables are loaded directly from process environment.

Key variables:

- `LCS_DATABASE_URL` - SQLite URL for baseline storage.
- `LCS_STORAGE_ROOT` - root directory for storage layout (`sqlite`, `media`, `avatars`, `uploads`, `rfid`, `backups`, `logs`, `incidents`).
