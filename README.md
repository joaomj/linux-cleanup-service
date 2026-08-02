# linux-cleanup-service

Run one safe storage cleanup pass after the first interactive Bash shell of
each day.

The service manages OpenCode session data, the OpenCode update, selected user
caches, and journal size reporting. It keeps all thresholds in a user
environment file.

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
- Rotates and vacuums existing system journal files.

Open a new Bash shell after installation. The first shell starts the job in the
background. The shell prints the last result.

## Configuration

Edit:

```text
~/.config/linux-cleanup-service/environment
```

The default values include:

```text
SESSION_RETENTION_DAYS=7
UV_CACHE_MAX_SIZE=1GiB
BRAVE_CACHE_MAX_SIZE=2GiB
JOURNAL_WARN_SIZE=100MiB
OPENCODE_DB_WARN_SIZE=2GiB
```

The service reads this file once at the start of each run. Process environment
variables take precedence over the file.

The size parser accepts `B`, `KB`, `KiB`, `MB`, `MiB`, `GB`, and `GiB`.

## Daily Work

The service performs these actions once per calendar day:

1. Upgrade OpenCode with its standalone installer.
2. Measure the Brave, UV, and npm caches.
3. Run `uv cache prune` above the UV threshold.
4. Clear the Brave cache above its threshold when Brave is stopped.
5. Skip Brave cleanup and report a warning when Brave is running.
6. Back up the OpenCode database before session deletion.
7. Delete session trees inactive for seven days.
8. Checkpoint SQLite and vacuum free pages when safe.
9. Rotate OpenCode backups and logs.
10. Measure system and user journal usage.

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
