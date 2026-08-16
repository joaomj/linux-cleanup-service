# linux-cleanup-service

Run one safe storage cleanup pass after the first interactive Bash shell of
each day.

The service manages OpenCode session data, system package updates, selected user
caches, and journal size reporting. It supports user settings in an environment
file.

## Install

Run:

```bash
./scripts/install
```

The installer:

- Installs a systemd user service.
- Adds a small startup hook to `~/.bashrc`.
- Creates `~/.config/linux-cleanup-service/environment`.
- Installs a root journald drop-in with `sudo`.
- Installs a root sudoers drop-in that allows the daily update commands without
  a password.
- Rotates and vacuums existing system journal files.

The installer asks for the sudo password when it needs it. Open a new Bash
shell after installation. The first shell starts the job in the background.
The shell prints the last result.

## Configuration

Edit:

```text
~/.config/linux-cleanup-service/environment
```

The default values include:

```text
SESSION_RETENTION_DAYS=7
TEMP_ROOT=/tmp/opencode
TEMP_RETENTION_DAYS=7
UV_CACHE_MAX_SIZE=1GiB
BRAVE_CACHE_MAX_SIZE=2GiB
JOURNAL_WARN_SIZE=100MiB
OPENCODE_DB_WARN_SIZE=2GiB
APT_UPDATES_ENABLED=true
SNAP_UPDATES_ENABLED=true
```

The service reads this file once at the start of each run. Process environment
variables take precedence over the file.

The size parser accepts `B`, `KB`, `KiB`, `MB`, `MiB`, `GB`, and `GiB`.

## Daily Work

The service performs these actions once per calendar day:

1. Run `sudo -n apt-get update`.
2. Run `sudo -n apt-get upgrade -y` when the APT update succeeds.
3. Run `sudo -n snap refresh`.
4. Upgrade OpenCode with its standalone installer.
5. Measure the Brave, UV, and npm caches.
6. Run `uv cache prune` above the UV threshold.
7. Clear the Brave cache above its threshold when Brave is stopped.
8. Skip Brave cleanup and report a warning when Brave is running.
9. Back up the OpenCode database before session deletion.
10. Delete session trees inactive for seven days.
11. Checkpoint SQLite and vacuum free pages when safe.
12. Rotate OpenCode backups and logs.
13. Measure system and user journal usage.

APT and Snap updates use non-interactive `sudo`. The installer creates the
root file `/etc/sudoers.d/90-linux-cleanup-service`, which allows exactly
these commands and the system journal rotate and vacuum operations without a
password. If `sudo` still needs a password, the service records a warning and
continues the remaining cleanup.

## Passwordless Updates

Regenerate or inspect the sudoers rule:

```bash
python3 ~/.local/libexec/linux-cleanup-service/config.py sudoers-config
```

If the installer could not use `sudo`, apply the rule manually:

```bash
tmp="$(mktemp)"
python3 "$HOME/.local/libexec/linux-cleanup-service/config.py" sudoers-config > "$tmp"
sudo install -D -m 440 -o root -g root "$tmp" /etc/sudoers.d/90-linux-cleanup-service
rm -f "$tmp"
```

The rule names the current user and grants no shell. It covers only
`apt-get update`, `apt-get upgrade -y`, `snap refresh`, `journalctl --rotate`,
and `journalctl --vacuum-size=<limit>`. Regenerate the rule after changing
`JOURNAL_SYSTEM_MAX_USE`, because the vacuum size is part of the command.

Account-level runs skip tasks and metrics that the account cannot inspect or
execute, such as system journal details or root-only package updates. These
tasks appear in the `skipped` field of the JSON status record and do not make a
successful cleanup a warning. Failures on resources owned by the account still
appear as warnings or errors.

The service never deletes OpenCode sessions without a successful database
backup. It uses `opencode session delete`, not direct event-table deletion.

## Status

Print the current status:

```bash
python3 ~/.local/libexec/linux-cleanup-service/status.py
```

Inspect the full record:

```bash
python3 ~/.local/libexec/linux-cleanup-service/status.py --json
```

Run a non-mutating inspection:

```bash
python3 ~/.local/libexec/linux-cleanup-service/cleanup.py --dry-run --force
```

Run a manual cleanup outside the daily gate:

```bash
systemctl --user start linux-cleanup.service
```

## Journal Limit

The default root drop-in uses:

```ini
[Journal]
Compress=yes
SystemMaxUse=80M
SystemMaxFileSize=8M
RuntimeMaxUse=16M
RuntimeMaxFileSize=8M
```

The 80 MiB persistent limit keeps journal usage below the requested 100 MiB
target. Active files can cause a small temporary excess.

If the installer cannot use `sudo`, apply the root setting manually:

```bash
tmp="$(mktemp)"
python3 "$HOME/.local/libexec/linux-cleanup-service/config.py" journal-config > "$tmp"
sudo install -D -m 644 "$tmp" /etc/systemd/journald.conf.d/90-linux-cleanup-service.conf
rm -f "$tmp"
sudo systemctl restart systemd-journald
sudo journalctl --rotate
vacuum_size="$(python3 "$HOME/.local/libexec/linux-cleanup-service/config.py" journal-vacuum-size)"
sudo journalctl --vacuum-size="$vacuum_size"
```

## Uninstall

Run:

```bash
./scripts/uninstall
```

The command removes installed code, the user unit, and the Bash hook. It keeps
configuration, state, and backups.

## Development

Run the local checks:

```bash
./scripts/verify
```

Do not place live database backups or status files in this repository.
