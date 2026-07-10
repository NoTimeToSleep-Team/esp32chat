# Security Policy

## Supported versions

ESP32Chat is currently an alpha project. Security fixes are applied to the latest `main` branch. Old prereleases and unmaintained snapshots should be considered unsupported.

| Version | Security support |
|---|---|
| Latest `main` | Best effort |
| Current prerelease | Best effort |
| Older snapshots | No |

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose accounts, credentials, sessions, private messages, devices, or server control.

Use GitHub's private vulnerability reporting page:

`https://github.com/NoTimeToSleep-Team/esp32chat/security/advisories/new`

Include:

- Affected commit or release.
- A clear description of the impact.
- Reproduction steps or proof of concept.
- Required configuration and hardware.
- Suggested mitigation, when available.
- Whether the issue is already public.

The maintainers will acknowledge a complete report when available, investigate it on a best-effort basis, and coordinate disclosure when a fix is ready. Because this is a volunteer alpha project, no guaranteed response or remediation time is promised.

## Handling secrets

Never commit or publish:

- Wi-Fi SSIDs and passwords.
- Session tokens or cookies.
- Account passwords.
- API keys and private keys.
- Private server addresses or identifying logs.
- Production databases or backups.

If a secret is committed, remove it from use immediately and rotate it. Deleting the file from the latest commit is not sufficient because Git history may still contain it.

## Scope note

The repository contains defensive security controls, but it has not undergone a formal security audit or external penetration test. Do not expose an alpha deployment directly to the public internet without independent review and appropriate network controls.
