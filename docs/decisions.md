# Decisions

## Use a User Service

Run the cleanup as a systemd user service. This gives the job the same user
identity and paths as OpenCode. The Bash hook starts it after the first shell
opens.

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

## Use Scoped Passwordless Sudo

Grant the service passwordless root access only to the exact commands it runs:
`apt-get update`, `apt-get upgrade -y`, `snap refresh`, and `journalctl`
rotate and vacuum. The sudoers drop-in names the user and the exact command
lines, so the daily job runs unattended without opening a general shell.
