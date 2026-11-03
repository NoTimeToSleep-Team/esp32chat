# USB root key (physical SSH gate)

## What it does

The USB stick is a physical key for root SSH:

- one or more USB partitions are enrolled by UUID/serial and a random marker
  token;
- an enrolled USB stick carries a marker (`LC_ROOT_KEY.json`) and can carry
  public SSH keys (`*.pub`);
- an `udev` rule starts `lc-usb-key@<device>.service` when the enrolled stick is
  inserted; the helper validates the marker and starts `ssh.service`;
- removing the stick stops the gate and closes the SSH daemon again.

The web application and the `localchat` account cannot run the helper. It is a
root-only local tool, like `lc-operator`.

This is **not** a replacement for normal SSH authentication: the stick is the
physical presence factor, and root still logs in with an OpenSSH key listed in
`/root/.ssh/authorized_keys`. The helper sets:

```text
PermitRootLogin prohibit-password
PubkeyAuthentication yes
```

in `/etc/ssh/sshd_config.d/10-lc-root-key.conf`.

The gate controls the SSH daemon as a whole. While the stick is absent, normal
(non-root) SSH logins are closed too; when it is inserted, the existing password
or key rules for those users still apply.

## Install

The setup wizard asks:

```text
Add a USB root SSH key (SSH opens only while the key is inserted)?
```

Choose **yes**, finish the install, then insert the USB stick when the installer
asks. If the stick contains one or more `*.pub` files, they are imported into
`/root/.ssh/authorized_keys`. If it contains none, the helper can create a new
ed25519 key on the stick.

If the feature is enabled but enrollment fails (no stick, no `.pub`, etc.), the
installer leaves SSH closed and prints:

```bash
sudo lc keys
```

Use the local console or an already-open SSH session to enroll a key later.
Because enrollment stops the SSH daemon, do it from the local console when
possible; if you run it over SSH, the current session may survive but new
connections will stay closed until the USB key is inserted.

## Usage

Insert the enrolled USB stick into the Raspberry Pi. The SSH daemon starts.
Connect normally with a private key that matches one of the imported public
keys:

```bash
ssh -i ~/.ssh/id_ed25519 root@<pi-address>
```

Remove the stick to stop the SSH daemon. Existing sessions are not forcibly
killed on all OpenSSH versions; close them explicitly if the physical gate must
also terminate current sessions.

## Key manager

```bash
sudo lc keys
```

The menu includes:

- **Show root SSH public keys** - every key in `/root/.ssh/authorized_keys`,
  with type, SHA256 fingerprint and comment;
- **Add key(s) from a USB stick** - import `*.pub` files and enroll the stick as
  a physical key;
- **Create a new key on a USB stick** - generate an ed25519 private/public pair
  on the stick and import the public key;
- **Remove a root SSH key** - remove any key from the root authorized-keys file;
- **Show/remove USB physical keys** - manage enrolled physical sticks;
- **Show SSH gate status**.

Non-interactive commands are also available:

```bash
sudo lc keys list
sudo lc keys add --device /dev/sda1
sudo lc keys new
sudo lc keys remove 1
sudo lc keys usb-list
sudo lc keys usb-remove <id-or-uuid>
sudo lc keys status
```

If you choose "Create a new key on a USB stick", the private key stays in
`lc-root-key/id_ed25519` on the stick. Copy it to your computer before relying
on it and keep a secure backup. The stick is both the physical presence factor
and the transport for that private key; a copied private key does not bypass the
physical gate.

## Files

```text
/etc/lc-root-key/state.json                  enrolled USB tokens (0600, root)
/root/.ssh/                                  root SSH directory (0700, root)
/root/.ssh/authorized_keys                   root SSH public keys (0600, root)
/etc/udev/rules.d/70-lc-usb-key.rules         generated, one line per token
/etc/systemd/system/lc-usb-key@.service       generated gate unit
/etc/ssh/sshd_config.d/10-lc-root-key.conf    root key-only policy
/usr/local/sbin/lc-usb-key                    installed helper used by udev
/opt/local-chat-server/scripts/lc-usb-key.py  source implementation
```

The marker token is stored in plain text on the USB stick. The server stores
only its SHA-256 hash; validation also checks the partition UUID and serial.
A cloned USB stick with the same UUID/serial and copied marker is a copy of the
physical key, so protect and back up the original.

## Recovery

- Lost or broken USB stick: use the local console/HDMI keyboard, run
  `sudo lc keys`, remove the old USB token or add a new key. SSH remains closed
  until a valid physical key is inserted.
- No root SSH key yet: log in locally and run `sudo lc keys` (or
  `sudo lc keys new` with a USB stick).
- If `openssh-server` is missing, install it with
  `sudo apt-get install openssh-server`, then run `sudo lc keys`.
- The installer/updates never delete `/etc/lc-root-key`; `lc uninstall` does not
  remove the SSH gate automatically. Remove it explicitly with
  `sudo lc keys remove-all-gate` (or `sudo lc-usb-key remove-all-gate` after the
  app has been uninstalled) if SSH should be permanently closed.

## Filesystem support

The USB partition must have a filesystem UUID and be supported by the running
kernel: FAT32 (`vfat`), exFAT (when the kernel/exfat package is present),
ext2/3/4 or NTFS. The helper mounts it with `nosuid,nodev,noexec`; for
enrollment it uses read/write, for opening it remounts read-only.
