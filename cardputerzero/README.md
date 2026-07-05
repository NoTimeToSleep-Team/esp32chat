# CardputerZero Port

This directory contains the Linux handheld port assets for M5CardputerZero.

## Scope

- Server target: M5CardputerZero can run the existing FastAPI/nginx stack using `server/scripts/install_cardputerzero.sh`.
- Client target: `apps/local_chat_portal/` provides an AppBuilder-compatible launcher package that opens the existing Local Chat SPA on the device.

## Why a Browser Launcher

The project already ships a complete web SPA (`server/app/static/app.js`, `server/app/static/app.css`, `server/app/templates/index.html`) covering chat, support, devices, account, and admin workflows.

For CardputerZero, the minimal real port is to reuse that proven SPA rather than invent a second Linux-native chat UI that would drift from the main product surface.

## Local-First Usage

1. Install the server on CardputerZero:

```bash
sudo bash server/scripts/install_cardputerzero.sh
```

2. Ensure the server is healthy:

```bash
curl -fsS http://127.0.0.1/health
```

3. Build/package the launcher app with CardputerZero AppBuilder.
4. Launch the portal client; it targets `http://127.0.0.1:8000/` by default.

## Remote Usage

Set `LOCAL_CHAT_SERVER_URL` before launching if the handheld should connect to another host instead of its own local server.
