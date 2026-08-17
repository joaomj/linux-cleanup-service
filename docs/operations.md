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
OpenCode, prune UV, clear Brave, create backups, delete sessions, or vacuum
SQLite. A normal run attempts SQLite vacuum and waits for the configured busy
timeout if OpenCode has the database open. It reports a warning if SQLite stays
busy.

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
