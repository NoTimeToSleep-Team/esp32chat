# GitHub repository setup checklist

The included scripts automate the changes supported by GitHub CLI. Review the commands before running them.

## 1. Apply the files

Copy this overlay into the root of a local clone or apply the supplied patch:

```bash
git apply esp32chat-community-update.patch
git diff --check
git status
```

The patch replaces the root README and adds community, branding, issue-template, and release files. It does not move existing source or internal project files.

## 2. Review the license

The package includes the MIT License with `NoTimeToSleep Team` as the copyright holder. Publish it only if the team owns the code or has permission to distribute all included code under MIT. Third-party code and assets must retain their own notices.

## 3. Commit and push

```bash
git switch -c community/repository-refresh
git add README.md README.ru.md LICENSE CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md SUPPORT.md CHANGELOG.md GITHUB_SETUP.md RELEASE_NOTES_v0.8.0-alpha.md .github docs/assets tools/community
git commit -m "Improve repository presentation and contribution workflow"
git push -u origin community/repository-refresh
```

Review the pull request and merge it after CI passes.

## 4. Configure GitHub

Install and authenticate GitHub CLI, then run one of:

```powershell
powershell -ExecutionPolicy Bypass -File tools/community/configure-github.ps1
```

```bash
bash tools/community/configure-github.sh
```

The script:

- Sets a clearer repository description.
- Enables Issues and Discussions.
- Adds focused repository topics.
- Creates contribution labels.
- Creates five starter issues if their titles do not already exist.
- Renames the existing `beta` prerelease and applies the prepared release notes.
- Attempts to update the organization description when the authenticated account has permission.

## 5. Manual GitHub settings

Some useful settings are not handled reliably through the public CLI/API:

1. Open **Settings → General → Social preview**.
2. Upload `docs/assets/esp32chat-social-preview.png`.
3. Open **Settings → Code security and analysis**.
4. Enable **Private vulnerability reporting** and available secret scanning options.
5. Open **Settings → Branches / Rulesets**.
6. Protect `main` and require the `software-verification` workflow before merging.
7. Pin ESP32Chat on the organization profile.

## 6. Organization profile

Recommended organization description:

> Open-source hardware and local-first software for ESP32, M5Stack, Flipper Zero, and Raspberry Pi.

For a full organization profile, create or update the special public repository named `.github` and place a profile README at `profile/README.md`.

## 7. Add real media

The included banner is branding, not proof of working hardware. Before promotion, add:

- One photograph showing the Raspberry Pi server and a supported handheld client.
- One browser screenshot with private information removed.
- A short GIF or video showing a message sent between two clients.

Do not imply a device was tested unless the test was actually performed.
