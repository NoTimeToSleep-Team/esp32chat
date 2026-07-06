# Local Chat Portal for CardputerZero

This is an AppBuilder-compatible launcher for the existing Local Chat SPA.

It ships a small mode-switch page with two actions:

- `Server mode` opens the local server on `http://127.0.0.1:8000/`
- `Client mode` opens a configurable remote server URL

The remote URL is stored in browser `localStorage`, so after the first change it persists between launches.

## Browser Resolution

The launcher tries, in order:

1. `LOCAL_CHAT_BROWSER` if provided
2. `chromium-browser`
3. `chromium`
4. `cog`
5. `xdg-open`

## Packaging Model

This app is marked as `legacy-deb-only` because it launches a standalone browser process instead of exporting an LVGL `app_main()` entrypoint.
