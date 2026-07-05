# Deploy to M5CardputerZero

M5CardputerZero is a Linux handheld based on Raspberry Pi CM0. The server deployment path is the same as for Raspberry Pi targets.

## Server Install

```bash
sudo bash ./scripts/install_cardputerzero.sh
```

This wrapper seeds `config/app.env` from `config/cardputerzero.env.example` on first install.

## Client Pairing

For the handheld client launcher, see:

- `cardputerzero/README.md`
- `cardputerzero/apps/local_chat_portal/`

The intended local-first mode is:

1. Install the server on the device.
2. Keep the server listening on `127.0.0.1:8000` behind nginx.
3. Launch the CardputerZero portal client, which opens the existing SPA against `http://127.0.0.1:8000/` by default.

## Verification

```bash
sudo systemctl status local-chat-server --no-pager
curl -fsS http://127.0.0.1/health
```
