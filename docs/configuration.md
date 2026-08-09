# Configuration Reference

The service loads defaults from `src/config.py` and then reads:

```text
~/.config/linux-cleanup-service/environment
```

Process environment variables override file values. The file uses simple
`KEY=VALUE` lines. It does not run shell code.

## Retention

| Variable | Default | Meaning |
| --- | --- | --- |
| `SESSION_RETENTION_DAYS` | `7` | Delete inactive session trees after this many days. |
| `TEMP_ROOT` | `/tmp/opencode` | Root directory for temporary OpenCode workspaces. |
| `TEMP_RETENTION_DAYS` | `7` | Delete inactive temporary workspaces after this many days. |
| `OPENCODE_BACKUP_MAX_COUNT` | `2` | Maximum number of compressed database backups. |
| `OPENCODE_BACKUP_RETENTION_DAYS` | `14` | Maximum backup age. |
| `OPENCODE_BACKUP_MAX_SIZE` | `4GiB` | Aggregate backup size target. |
| `OPENCODE_LOG_RETENTION_DAYS` | `14` | OpenCode log retention. |

## Storage Thresholds

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENCODE_DB_WARN_SIZE` | `2GiB` | Warn when the live database exceeds this size. |
| `UV_CACHE_MAX_SIZE` | `1GiB` | Run `uv cache prune` above this size. |
| `BRAVE_CACHE_MAX_SIZE` | `2GiB` | Clear the Brave cache above this size. |
| `NPM_CACHE_WARN_SIZE` | `1GiB` | Warn when the npm cache exceeds this size. |
| `JOURNAL_WARN_SIZE` | `100MiB` | Warn when either journal measurement exceeds this size. |
| `SQLITE_VACUUM_MIN_SIZE` | `128MiB` | Minimum reclaimable SQLite space for `VACUUM`. |

The service ignores Zed files.

## System Updates

| Variable | Default | Meaning |
| --- | --- | --- |
| `APT_UPDATES_ENABLED` | `true` | Run `apt-get update` and `apt-get upgrade -y`. |
| `SNAP_UPDATES_ENABLED` | `true` | Run `snap refresh`. |

The service runs these commands with non-interactive `sudo`. Set either value
to `false` to disable that update action.

## Journal Settings

| Variable | Default |
| --- | --- |
| `JOURNAL_SYSTEM_MAX_USE` | `80M` |
| `JOURNAL_SYSTEM_MAX_FILE_SIZE` | `8M` |
| `JOURNAL_RUNTIME_MAX_USE` | `16M` |
| `JOURNAL_RUNTIME_MAX_FILE_SIZE` | `8M` |

The installer uses these values to generate the root journald drop-in.

## Paths

The following values are configurable for testing or alternate layouts:

- `OPENCODE_COMMAND`
- `OPENCODE_DB_PATH`
- `OPENCODE_LOG_DIR`
- `OPENCODE_SESSION_DIFF_DIR`
- `UV_CACHE_PATH`
- `BRAVE_CACHE_PATH`
- `NPM_CACHE_PATH`
