# Server performance notes

The portal is designed for one Raspberry Pi, a few dozen chat clients and
SQLite.  The goal is stable latency under small bursts, not horizontal scaling.

## Execution model

- **One uvicorn process.**  Realtime state (the WebSocket broker, presence and
  the in-memory rate limiters) lives in the process.  Starting multiple
  uvicorn workers would split that state: a message sent through worker A
  would not reach a WebSocket connected to worker B.  A multi-process setup
  would need a cross-process event bus and sticky sessions; that is not a
  sensible default for a local chat server.
- **Thread pool for synchronous work.**  FastAPI runs regular `def` route
  handlers in AnyIO's thread pool.  The previous code declared nearly every
  route as `async def` while calling blocking SQLite, PBKDF2 and file code, so
  one slow request could stall the event loop and every WebSocket.  Hot route
  handlers and WebSocket database operations now run in the pool.
- **Bounded concurrency.**  `LCS_THREADPOOL_SIZE` controls the pool size.
  The default is four threads per CPU core, clamped to 8..32 (8 on a 2-core
  Raspberry Pi).  This is enough to overlap SQLite reads and PBKDF2 hashing
  without creating an unbounded number of SQLite connections.  Set it in
  `config/app.env` only if profiling shows a reason:

  ```dotenv
  LCS_THREADPOOL_SIZE=12
  ```

## SQLite

- The migration runner enables WAL.  WAL lets readers continue while a writer
  commits, which matters for chat history and `/chat/api/updates`.
- New connections use `busy_timeout=5000`, `synchronous=NORMAL`, a small
  in-memory page cache and `temp_store=MEMORY` (see
  `server/app/db/connection.py`).  `synchronous=NORMAL` is the WAL
  recommendation: a power loss can lose the last transaction, but the
  database does not become corrupt.
- `connect_sqlite()` returns a `ClosingConnection`.  Unlike the standard
  `sqlite3.Connection`, its context manager commits/rolls back **and closes**
  the file handle.  All service `_connect()` methods return it, so the
  `with self._connect() as connection:` request scopes cannot leak one
  descriptor per request.
- Migration `0036_performance_indexes.sql` adds indexes for per-chat message
  order (`chat_id, id`), the cross-chat update feed (`created_at_ms`) and
  "My Files" (`owner_user_id, created_at_ms`).

The board database currently has a single writer (the server process), so a
connection pool is not needed yet.  If write volume grows, the next step is a
small pooled connection layer, not more uvicorn workers.

## Quick checks

Health and process state:

```bash
curl -fsS http://127.0.0.1:18080/health
systemctl status local-chat-server --no-pager
```

Check the effective thread budget in the service log:

```bash
journalctl -u local-chat-server -n 20 --no-pager | grep 'Application startup'
```

Simple query-plan check (SQLite shell or Python):

```sql
EXPLAIN QUERY PLAN
SELECT msg.body_text
FROM chat_messages msg
WHERE msg.chat_id = 1
ORDER BY msg.id DESC
LIMIT 1;
```

The plan should use `idx_chat_messages_chat_id_id` and should not contain
`USE TEMP B-TREE FOR ORDER BY`.

## What not to do

- Do not add `--workers N` to the systemd unit without solving realtime
  fan-out.  It will look faster in a synthetic HTTP benchmark and then break
  live chat delivery.
- Do not raise the thread-pool size to hundreds.  SQLite writers still
  serialize, and each thread may hold a connection and a page cache.
