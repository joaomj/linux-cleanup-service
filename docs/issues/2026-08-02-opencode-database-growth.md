# OpenCode Database Growth

## Context

OpenCode issue `#33356` reports unbounded growth in the SQLite `event` table.
The issue reports databases larger than 13 GiB. Follow-up measurement on a
51.3 GiB instance (issue comment, 2026-08-15) shows the `event` table is
43.96 GiB of that total, against 4.7 GiB of durable state.

The local OpenCode database is:

```text
~/.local/share/opencode/opencode.db
```

## Root Cause

Two independent growth mechanisms are stacked in the event log:

1. Full-snapshot `message.updated.1` events. Every update persists a complete
   message snapshot, and all historical snapshots are retained forever.
2. Re-serialized `summary.diffs` on user messages. This derived field carries
   per-file diffs with full patch text. OpenCode re-attaches it wholesale on
   each summarization pass and re-serializes it in the `MessageUpdated` event.
   It produces the multi-megabyte tail: one message with a 9 MB final state
   wrote 1,953 MB across 236 update events.

The event log has no retention limit, and SQLite `VACUUM` cannot reclaim live
rows.

Partial pruning inside a session is not safe by default. OpenCode replay
asserts sequence contiguity and aggregate reads have no gap detection, so
deleting some events of a session creates a silent hole. Whole-session
deletion is the only safe form of pruning without an upstream resync signal.

## Working Mitigation

The service retains sessions that had activity during the last seven days. It
backs up the full database before deleting older root session trees. It uses
OpenCode's supported session deletion command so related event aggregates are
removed by the application. Whole-session deletion also removes both growth
mechanisms above, because their data lives in the same event rows.

The service warns above 2 GiB. It does not delete sessions newer than the
retention period to enforce a size limit.

## Related Links

- Issue: https://github.com/anomalyco/opencode/issues/33356
- Diffs side-table issue: https://github.com/anomalyco/opencode/issues/42748
- Proposed upstream fix: https://github.com/anomalyco/opencode/pull/36710
