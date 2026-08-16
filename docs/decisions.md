# Decisions

## Use a User Service

Run the cleanup as a systemd user service (Linux) or a launchd user job
(macOS). This gives the job the same user identity and paths as OpenCode. The
shell hook starts it after the first shell opens.

## Support macOS Through Platform Detection

Keep one codebase and detect the platform at runtime with `sys.platform`
checks, and in the installer with `uname`. The alternative was a separate
macOS branch, which would require re-porting every future feature. The service
keeps the Linux name and uses the name `macos-cleanup-service`, a launchd job,
and macOS paths on Apple hardware. Linux-only actions skip cleanly on macOS.

## Use Full Database Backups

Create a full SQLite backup before deleting stale sessions. This gives a
restore point without directly editing event rows.

## Skip Active Brave Cleanup

Do not clear Brave cache files while Brave runs. The service reports a warning
and retries on the next daily run.

## Keep the Database Limit Warning-Only

Do not enforce a SQLite page limit. A hard limit can make OpenCode fail with a
disk-full error. The service reports the condition and keeps the seven-day
retention rule.

## Use Scoped Passwordless Sudo (Linux)

Grant the service passwordless root access only to the exact commands it runs:
`apt-get update`, `apt-get upgrade -y`, `snap refresh`, and `journalctl`
rotate and vacuum. The sudoers drop-in names the user and the exact command
lines, so the daily job runs unattended without opening a general shell. This
decision applies to Linux only.
