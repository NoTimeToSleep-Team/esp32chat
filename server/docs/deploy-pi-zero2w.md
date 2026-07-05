# Deploy to Raspberry Pi Zero 2 W

This target uses the standard Linux server package with the Pi Zero 2 W specific env template.

## Recommended Install

```bash
sudo bash ./scripts/install_pi_zero2w.sh
```

This wrapper is identical to `install_pi.sh`, but it seeds `config/app.env` from `config/pi-zero2w.env.example` on first install.

## Notes

- CPU/RAM target: BCM2710A1 / Cortex-A53, 512MB RAM.
- The server still runs as a single `uvicorn` process via systemd.
- Keep nginx enabled and `LCS_HOST=127.0.0.1` so nginx remains the public entry point.

## Post-Install Verification

```bash
sudo systemctl status local-chat-server --no-pager
curl -fsS http://127.0.0.1/health
curl -fsS http://127.0.0.1/health/ready
```
