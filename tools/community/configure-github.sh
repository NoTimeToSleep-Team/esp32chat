#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-NoTimeToSleep-Team/esp32chat}"
ORG="${REPO%%/*}"

command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) is required." >&2; exit 1; }
gh auth status >/dev/null

DESCRIPTION="Self-hosted local chat for Raspberry Pi with web, M5Cardputer, M5StickC Plus 2, T-Embed and Flipper Zero clients."
ORG_DESCRIPTION="Open-source hardware and local-first software for ESP32, M5Stack, Flipper Zero, and Raspberry Pi."

gh repo edit "$REPO" --description "$DESCRIPTION" --enable-issues --enable-discussions

for topic in esp32 raspberry-pi self-hosted local-first chat fastapi websocket m5stack m5cardputer flipper-zero; do
  gh repo edit "$REPO" --add-topic "$topic"
done

while IFS='|' read -r name color description; do
  gh label create "$name" --repo "$REPO" --color "$color" --description "$description" --force
done <<'LABELS'
needs-triage|D4C5F9|Needs maintainer review
good first issue|7057FF|Suitable for a first contribution
hardware-test|0E8A16|Physical hardware validation
documentation|0075CA|Documentation change
bug|D73A4A|Something is not working
enhancement|A2EEEF|New feature or improvement
help wanted|008672|Community help is welcome
LABELS

create_issue_if_missing() {
  local title="$1" body_file="$2" labels="$3"
  if gh issue list --repo "$REPO" --state all --limit 200 --json title --jq '.[].title' | grep -Fqx "$title"; then
    echo "Issue already exists: $title"
  else
    gh issue create --repo "$REPO" --title "$title" --body-file "$body_file" --label "$labels"
  fi
}

create_issue_if_missing "[Good first issue] Improve Windows server installation instructions" ".github/seed-issues/01-windows-installation.md" "documentation,good first issue,help wanted"
create_issue_if_missing "[Good first issue] Add Spanish README translation" ".github/seed-issues/02-spanish-translation.md" "documentation,good first issue,help wanted"
create_issue_if_missing "[Hardware test] Validate the M5StickC Plus 2 client" ".github/seed-issues/03-m5stick-hardware-test.md" "hardware-test,help wanted"
create_issue_if_missing "[Documentation] Record a Raspberry Pi Zero 2 W installation video" ".github/seed-issues/04-pi-zero-video.md" "documentation,help wanted"
create_issue_if_missing "[Feature] Prototype a browser-based firmware installer" ".github/seed-issues/05-browser-flasher.md" "enhancement,help wanted"

if gh release view beta --repo "$REPO" >/dev/null 2>&1; then
  gh release edit beta --repo "$REPO" --title "v0.8.0-alpha — Raspberry Pi server preview" --notes-file RELEASE_NOTES_v0.8.0-alpha.md --prerelease
else
  echo "Release tag 'beta' was not found; release update skipped."
fi

if gh api --method PATCH "/orgs/$ORG" -f description="$ORG_DESCRIPTION" >/dev/null 2>&1; then
  echo "Organization description updated."
else
  echo "Organization description was not changed (owner permission may be required)."
fi

echo "GitHub repository setup completed for $REPO."
