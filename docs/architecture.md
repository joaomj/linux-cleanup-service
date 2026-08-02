# Architecture

The service uses a systemd user unit and a Bash startup hook.

```text
interactive Bash shell
        |
        +--> systemctl --user start --no-block
        |          |
        |          +--> linux-cleanup.service
        |                       |
        |                       +--> cleanup.py
        |                              |
        |                              +--> OpenCode updater
        |                              +--> cache measurements
        |                              +--> SQLite backup and session deletion
        |                              +--> journal measurements
        |                              +--> atomic status.json
        |
        +--> status.py --> prints status.json
```

The Bash hook starts the service on every interactive shell. The service uses
an exclusive file lock and a local-date marker. Therefore only the first
successful start attempt of each day performs work.

The service runs as the user. It can manage user files and the user journal.
The installer uses `sudo` once to install the system journald limit.

## Database Safety

The service reads session candidates with a recursive SQLite query. It finds
root sessions whose complete descendant tree is older than the retention
period.

Before deletion, it creates a consistent online SQLite backup. It then calls
the supported OpenCode session deletion command for each root. OpenCode
recursively removes its child sessions and event aggregates.

The service never writes a direct `DELETE` statement to the OpenCode database.
