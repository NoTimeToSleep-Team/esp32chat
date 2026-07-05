# Local Chat Portal for CardputerZero

This is an AppBuilder-compatible launcher for the existing Local Chat SPA.

It does not duplicate the chat UI in a second native implementation. Instead, it opens the already-tested web portal that ships with the server.

## Default Target

- `http://127.0.0.1:8000/`

Override with:

```bash
LOCAL_CHAT_SERVER_URL=http://192.168.4.1:8000/ /usr/share/APPLaunch/bin/local-chat-portal
```

## Browser Resolution

The launcher tries, in order:

1. `LOCAL_CHAT_BROWSER` if provided
2. `chromium-browser`
3. `chromium`
4. `cog`
5. `xdg-open`

## Packaging Model

This app is marked as `legacy-deb-only` because it launches a standalone browser process instead of exporting an LVGL `app_main()` entrypoint.
