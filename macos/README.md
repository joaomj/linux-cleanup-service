# macos-cleanup-service

The macOS port of `linux-cleanup-service`. On macOS the service is named
`macos-cleanup-service` and is scheduled through launchd instead of systemd.

The installer at `../scripts/install` detects the platform and installs the
correct service manager automatically. There is no separate macOS installer.

## What is different on macOS

- The service name is `macos-cleanup-service`.
- A launchd user job replaces the systemd user unit.
- The startup hook targets `~/.zshrc` (macOS default shell).
- Process detection uses `pgrep` instead of `/proc`.
- Journal management is skipped because macOS has no systemd journal.
- Default paths follow macOS conventions:

| Item | Path |
| --- | --- |
| Configuration and state | `~/Library/Application Support/macos-cleanup-service/` |
| Installed code | `~/.local/libexec/macos-cleanup-service/` |
| OpenCode database | `~/.local/share/opencode/opencode.db` |
| Caches | `~/Library/Caches/` |
| Backups | `~/backups/opencode/` if it exists, else the state directory |

The service auto-detects an existing `~/backups/opencode/` directory and
manages backups there instead of moving them.

## Install

Run from the repository root:

```bash
./scripts/install
```

The installer:

- Installs the launchd user job `com.user.macos-cleanup-service`.
- Adds a startup hook to `~/.zshrc`.
- Creates `~/Library/Application Support/macos-cleanup-service/environment`
  from `config/macos.env` when no environment file exists yet.
- Uses the existing `~/backups/opencode/` directory when present.

The daily job runs on the first shell session of each day, not at a fixed
time. Later shells trigger the job again but the daily gate in `cleanup.py`
stops duplicate work.

## Configuration

Edit:

```text
~/Library/Application Support/macos-cleanup-service/environment
```

The installer writes the defaults from `config/macos.env` in the repository.
The default values include:

```text
SESSION_RETENTION_DAYS=7
OPENCODE_BACKUP_RETENTION_DAYS=14
OPENCODE_BACKUP_MAX_COUNT=2
OPENCODE_BACKUP_MAX_SIZE=4GiB
UV_CACHE_MAX_SIZE=1GiB
BRAVE_CACHE_MAX_SIZE=2GiB
OPENCODE_DB_WARN_SIZE=2GiB
OPENCODE_UPGRADE_ENABLED=false
OPENCODE_UPGRADE_METHOD=brew
```

Journal limit settings are not present because macOS has no systemd journal.

The service reads this file once at the start of each run. Process environment
variables take precedence over the file.

## Status

Print the current status:

```bash
python3 ~/.local/libexec/macos-cleanup-service/status.py
```

Inspect the full record:

```bash
python3 ~/.local/libexec/macos-cleanup-service/status.py --json
```

Run a non-mutating inspection:

```bash
python3 ~/.local/libexec/macos-cleanup-service/cleanup.py --dry-run --force
```

Run a manual cleanup outside the daily gate:

```bash
launchctl start com.user.macos-cleanup-service
```

## Uninstall

Run from the repository root:

```bash
./scripts/uninstall
```

The command removes installed code, the launchd job, and the shell hook. It
keeps configuration, state, and backups.

## Development

Run the local checks from the repository root:

```bash
./scripts/verify
```

Do not place live database backups or status files in this repository.
