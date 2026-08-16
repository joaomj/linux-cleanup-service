# Architecture

The service runs on Linux and macOS. On Linux it uses a systemd user unit and
a Bash startup hook. On macOS it uses a launchd user job and a zsh startup
hook.

```text
interactive shell
        |
        +--> start service (systemd on Linux, launchd on macOS)
        |          |
        |          +--> linux-cleanup.service / com.user.macos-cleanup-service
        |                       |
        |                       +--> cleanup.py
        |                              |
        |                              +--> APT and Snap updaters (Linux)
        |                              +--> OpenCode updater
        |                              +--> cache measurements
        |                              +--> SQLite backup and session deletion
        |                              +--> journal measurements (Linux)
        |                              +--> atomic status.json
        |
        +--> status.py --> prints status.json
```

The shell hook starts the service on every interactive shell. The service uses
an exclusive file lock and a local-date marker. Therefore only the first
successful start attempt of each day performs work.

The service runs as the user. It can manage user files and the user journal.
The daily APT and Snap actions use non-interactive `sudo` (Linux only). The
installer also uses `sudo` to install the system journald limit (Linux only).

The installer detects the platform with `uname`. On macOS the service:

- uses the name `macos-cleanup-service`
- installs a launchd job instead of a systemd unit
- adds the startup hook to `~/.zshrc` instead of `~/.bashrc`
- detects running processes with `pgrep` instead of `/proc`
- skips journal management because macOS has no systemd journal
- keeps configuration and state in `~/Library/Application Support`
- keeps caches in `~/Library/Caches`

The Python code detects the platform with `sys.platform` checks. Linux-only
actions such as APT, Snap, and journal management skip cleanly on macOS.

## Database Safety

The service reads session candidates with a recursive SQLite query. It finds
root sessions whose complete descendant tree is older than the retention
period.

Before deletion, it creates a consistent online SQLite backup. It then calls
the supported OpenCode session deletion command for each root. OpenCode
recursively removes its child sessions and event aggregates.

The service never writes a direct `DELETE` statement to the OpenCode database.