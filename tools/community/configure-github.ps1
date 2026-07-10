param(
    [string]$Repo = "NoTimeToSleep-Team/esp32chat"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required. Install it and run 'gh auth login'."
}

gh auth status | Out-Null

$org = $Repo.Split('/')[0]
$description = "Self-hosted local chat for Raspberry Pi with web, M5Cardputer, M5StickC Plus 2, T-Embed and Flipper Zero clients."
$orgDescription = "Open-source hardware and local-first software for ESP32, M5Stack, Flipper Zero, and Raspberry Pi."

gh repo edit $Repo --description $description --enable-issues --enable-discussions

$topics = @(
    "esp32", "raspberry-pi", "self-hosted", "local-first", "chat",
    "fastapi", "websocket", "m5stack", "m5cardputer", "flipper-zero"
)
foreach ($topic in $topics) {
    gh repo edit $Repo --add-topic $topic
}

$labels = @(
    @{ Name = "needs-triage"; Color = "D4C5F9"; Description = "Needs maintainer review" },
    @{ Name = "good first issue"; Color = "7057FF"; Description = "Suitable for a first contribution" },
    @{ Name = "hardware-test"; Color = "0E8A16"; Description = "Physical hardware validation" },
    @{ Name = "documentation"; Color = "0075CA"; Description = "Documentation change" },
    @{ Name = "bug"; Color = "D73A4A"; Description = "Something is not working" },
    @{ Name = "enhancement"; Color = "A2EEEF"; Description = "New feature or improvement" },
    @{ Name = "help wanted"; Color = "008672"; Description = "Community help is welcome" }
)
foreach ($label in $labels) {
    gh label create $label.Name --repo $Repo --color $label.Color --description $label.Description --force
}

function Add-IssueIfMissing {
    param(
        [string]$Title,
        [string]$BodyFile,
        [string]$Labels
    )

    $titles = gh issue list --repo $Repo --state all --limit 200 --json title --jq '.[].title'
    if ($titles -contains $Title) {
        Write-Host "Issue already exists: $Title"
        return
    }

    gh issue create --repo $Repo --title $Title --body-file $BodyFile --label $Labels
}

Add-IssueIfMissing "[Good first issue] Improve Windows server installation instructions" ".github/seed-issues/01-windows-installation.md" "documentation,good first issue,help wanted"
Add-IssueIfMissing "[Good first issue] Add Spanish README translation" ".github/seed-issues/02-spanish-translation.md" "documentation,good first issue,help wanted"
Add-IssueIfMissing "[Hardware test] Validate the M5StickC Plus 2 client" ".github/seed-issues/03-m5stick-hardware-test.md" "hardware-test,help wanted"
Add-IssueIfMissing "[Documentation] Record a Raspberry Pi Zero 2 W installation video" ".github/seed-issues/04-pi-zero-video.md" "documentation,help wanted"
Add-IssueIfMissing "[Feature] Prototype a browser-based firmware installer" ".github/seed-issues/05-browser-flasher.md" "enhancement,help wanted"

try {
    gh release view beta --repo $Repo | Out-Null
    gh release edit beta --repo $Repo --title "v0.8.0-alpha — Raspberry Pi server preview" --notes-file RELEASE_NOTES_v0.8.0-alpha.md --prerelease
} catch {
    Write-Warning "Release tag 'beta' was not found; release update skipped."
}

try {
    gh api --method PATCH "/orgs/$org" -f "description=$orgDescription" | Out-Null
    Write-Host "Organization description updated."
} catch {
    Write-Warning "Organization description was not changed. Organization-owner permission may be required."
}

Write-Host "GitHub repository setup completed for $Repo."
