# Camp Edition — isolated product branch

This directory is an experimental **Camp Edition** derived from
`D:\opencode\LC_RELEASE` at `c2a7c53`.

Rules:

- Do not modify `D:\opencode\LC_RELEASE` or its live board service.
- Work only inside `D:\opencode\LC_CAMP_EDITION`.
- The edition is additive: `server/app/camp/`, `1xxx_camp_*.sql`,
  `server/app/static/camp/`, camp tests and docs.
- Keep the core API/chat behavior intact; camp rules live in the camp module.
- No cloud dependency, no GPS, no face recognition, no AI child companion.
- Test with a disposable local DB/server only.

Source report:
`D:\opencode\LC_BACKUPS\camp-edition-deep-report-2026-11-13.md`
