# Security and installer fixes — 2026-11-09 (deep round)

This round covered a black-box deep pentest of the live `0.1.10` stand and a
full local regression/installer pass. The product findings below were fixed;
the remaining items are explicitly operator or deployment actions.

## Chat administration

- `set_member_permissions` now defaults every omitted flag to `False`. A
  partial request such as `{"restrict_members": false}` can no longer silently
  grant all the permissions the caller left out. The UI still sends the full
  flag map.
- `_has_permission` fails closed for malformed or non-object permission JSON.
  Legacy admin rows with no permissions blob keep the historical full-admin
  behaviour; every new row carries an explicit map.
- `delete_messages` is now enforced. A chat owner, or an admin holding that
  flag, can delete another member's message; an admin without the flag cannot.
  The HTTP endpoint no longer rejects every non-author before the service can
  apply the chat permission.

## Direct messages

- A DM remains an immutable two-member chat. Leaving a DM now only archives it
  for that participant instead of deleting their membership. The other side
  keeps the conversation and the exact-two-member invariant.
- Reopening the same DM from the chat search unarchives it for that participant
  and reuses the existing chat instead of creating a new one.

## Read state and enumeration

- `mark_read` ignores message ids that do not belong to the requested chat, so
  a foreign or stale id cannot advance the caller's read marker. Valid ids are
  still accepted.
- Registration now has a failure-only limiter (10 `login_taken`/`phone_taken`
  failures per IP in 10 minutes, then a 10-minute block). Normal registrations
  of free logins do not consume the budget.
- Private room-code joins are limited to 10 wrong codes per IP/chat in 10
  minutes. A successful join clears that key.
- Anonymous hardware pairing requests are limited to 10 per IP per minute.
- Moderators still get the user list needed for moderation, but it no longer
  includes `phone`, `registration_device_id` or `block_reason`; platform admins
  keep the full fields.

## Installer

- `lc uninstall --purge` now also removes:
  - `/usr/local/sbin/lc-operator` and `/usr/local/sbin/lc-usb-key`;
  - the USB root-key udev rule, systemd template and `/etc/lc-root-key`;
  - the `localchat` user and group;
  - `/var/log/lc-install.log`;
  - earlier `/opt/local-chat-server.removed-*` copies that still contain the
    database and `app.env`.
- The USB gate unit/rule/symlinks are also removed on a normal uninstall,
  because the application code they reference is gone. Data is still kept for
  a normal uninstall.
- The bootstrap logs when it installs from a local checkout and ignores
  `LC_TARBALL_URL`/`LC_VERSION` in that mode.
- The release tarball normalizes directory/file modes, so a tarball built from
  a WSL/drvfs checkout no longer ships `0777` files.

## Tests

- New regression suite: `tests/server/test_security_fixes_2026_11_09d.py`
  (29 checks): partial permissions, fail-closed JSON, DM leave/archive,
  `delete_messages`, foreign mark-read, registration/room-code/pairing limits,
  moderator field minimization.
- UI suites were brought back in line with the current product:
  - web login helpers pass a stable `device_id`;
  - removed `#chat-dm-btn` and old DM modal checks;
  - admin suite rewritten for the current `#l-btn` / `#tabs .chip` /
    `#content` page;
  - admin auto-login from an existing admin app session is accepted;
  - support suites seed their own ticket;
  - mobile suite seeds a scrollable chat list and a ticket;
  - unread-badge test opens another chat before seeding unread messages;
  - profile header comparison accepts the presence suffix;
  - ownership transfer back uses the new owner's token.

## Verification

- `test_security_fixes_2026_11_09d.py`: **29 passed, 0 failed**.
- Existing server suites: `09c` 38/38, `09b` 20/20, access 38/38 primarily;
  chat updates 10/10, device pairing 17/17, admin boundary 26/26, USB root key
  11/11.
- UI suites: all 15 pass individually against a disposable server
  (`ui_test` 24, mobile 28, devices 19, avatar 11, admin 13, voice 17,
  support 16, support SPA 18, chat create 16, gestures 32, groups 34, P1 34,
  P2 24, profile 33, automod 23).
- Installer on WSL Debian 13.5: fresh install from the current tarball,
  sha256 verification, systemd health, admin login and `lc uninstall --purge`
  with a simulated old `.removed-*` copy — **PASS**, no leftovers.

## Remaining operator/deployment items

- Guest-to-user DMs remain an intentional product policy (guests may open a DM
  and write to a regular user). The existing guest DM rate limit stays.
- F-09: `profile=test` exposes docs/OpenAPI; use `prod` or network filtering
  for wider deployments.
- F-10: old admin password remains in public Git history; a history rewrite
  requires a coordinated force-push.
- F-11: HTTP/query-string session tokens; TLS and signed/header-based media
  URLs remain deployment/UI work.
- A former platform admin attempting to transfer ownership to themselves still
  receives `409 self_transfer_forbidden` after the permission check; the
  operation is correctly refused, only the status code is less specific.
- The `.deb`/rpm/pacman packaging tree is still untracked WIP; it was not part
  of this round.
