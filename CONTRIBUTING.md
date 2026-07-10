# Contributing to ESP32Chat

Thank you for helping improve ESP32Chat. Contributions may include code, documentation, translations, hardware test reports, reproducible bug reports, and demonstration media.

## Before opening an issue

1. Search existing issues and pull requests.
2. Confirm that the problem still occurs on the latest `main` branch.
3. Remove passwords, Wi-Fi credentials, tokens, private addresses, and personal data from logs.
4. Use the closest issue template and provide exact reproduction steps.

Security vulnerabilities must be reported privately according to [SECURITY.md](SECURITY.md).

## Development setup

ESP32Chat requires Python 3.10 or newer for the server tooling.

```bash
git clone https://github.com/NoTimeToSleep-Team/esp32chat.git
cd esp32chat
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "./server[dev]"
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Run the verification sweep before submitting a pull request:

```bash
python docs/tools/run_software_verification_sweep.py --with-compileall
```

## Pull requests

- Keep each pull request focused on one problem.
- Explain what changed, why it changed, and how it was tested.
- Link the related issue when one exists.
- Update documentation when behavior, configuration, or supported hardware changes.
- Do not claim hardware verification unless the test was performed on the named physical device.
- Avoid unrelated formatting or generated-file changes.
- Preserve compatibility unless the pull request clearly documents a deliberate breaking change.

## Hardware test reports

A useful hardware report includes:

- Exact board and hardware revision.
- Firmware commit SHA.
- Toolchain and library versions.
- Build configuration and enabled compile-time options.
- Server model, operating system, and server commit SHA.
- Network topology and access-point details.
- Expected and observed behavior.
- Serial output or sanitized logs.
- Reproduction frequency and recovery procedure.

Use the **Hardware validation report** issue template.

## Commit messages

Use concise imperative messages. Examples:

```text
Fix Cardputer reconnect after Wi-Fi loss
Document Raspberry Pi Zero 2 W installation
Add M5StickC Plus 2 hardware validation log
```

## AI-assisted contributions

AI-assisted code and documentation are allowed, but the contributor remains responsible for the result. Review generated changes, understand their behavior, run the relevant checks, and disclose major AI-generated sections when this helps reviewers assess risk. Unverified claims, fabricated test results, and committed secrets are not acceptable.

## Conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
