# Operations

## View the Last Result

Run:

```bash
python3 ~/.local/libexec/linux-cleanup-service/status.py --json
```

View service logs:

```bash
journalctl --user -u linux-cleanup.service
```

## Test Without Changes

Run:

```bash
python3 ~/.local/libexec/linux-cleanup-service/cleanup.py --dry-run --force
```

The dry run measures current state and finds stale sessions. It does not update
APT, Snap, or OpenCode. It does not prune UV, clear Brave, create backups,
delete sessions, or vacuum SQLite.

## System Updates

The daily run uses these commands:

```bash
sudo -n apt-get update
sudo -n apt-get upgrade -y
sudo -n snap refresh
```

The service runs the APT upgrade only after the package-list update succeeds.
The installer creates the root file `/etc/sudoers.d/90-linux-cleanup-service`.
The file allows only these commands and the system journal rotate and vacuum
operations without a password. If an update still fails, the service records a
warning and continues its cleanup. The service does not ask for a password.

Inspect the current rule:

```bash
python3 ~/.local/libexec/linux-cleanup-service/config.py sudoers-config
```

Regenerate and reinstall the rule after changing `JOURNAL_SYSTEM_MAX_USE`,
because the vacuum size is part of the allowed command. To stop all updates,
set `APT_UPDATES_ENABLED=false` or `SNAP_UPDATES_ENABLED=false`.

## Retry After a Failure

Inspect the status and service log first. Fix the reported cause, then run:

```bash
systemctl --user reset-failed linux-cleanup.service
systemctl --user start linux-cleanup.service
```

The service is safe to retry. It creates a new backup before another deletion
attempt.

## Brave Cache

The service skips Brave cache deletion while a Brave process runs. Close Brave,
then start the service manually if an immediate retry is required.

## Database Backups

Backups are stored in:

```text
~/.local/state/linux-cleanup-service/backups/
```

They use `zstd` compression and mode `0600`. The service retains the newest
valid backup when the aggregate size target cannot be met.

## Change Thresholds

Edit the environment file and run a dry run:

```bash
$EDITOR ~/.config/linux-cleanup-service/environment
python3 ~/.local/libexec/linux-cleanup-service/cleanup.py --dry-run --force
```

Open a new shell or restart the user unit after configuration changes.
