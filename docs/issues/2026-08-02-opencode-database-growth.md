# OpenCode Database Growth

## Context

OpenCode issue `#33356` reports unbounded growth in the SQLite `event` table.
The issue reports databases larger than 13 GiB, with historical
`message.updated` snapshots as the main source of growth.

The local OpenCode database is:

```text
~/.local/share/opencode/opencode.db
```

## Root Cause

The event log keeps historical snapshots for session replay. The database has
no general event retention limit. SQLite `VACUUM` cannot reclaim live rows.

## Working Mitigation

The service retains sessions that had activity during the last seven days. It
backs up the full database before deleting older root session trees. It uses
OpenCode's supported session deletion command so related event aggregates are
removed by the application.

The service warns above 2 GiB. It does not delete sessions newer than the
retention period to enforce a size limit.

## Related Links

- Issue: https://github.com/anomalyco/opencode/issues/33356
- Proposed upstream fix: https://github.com/anomalyco/opencode/pull/36710
