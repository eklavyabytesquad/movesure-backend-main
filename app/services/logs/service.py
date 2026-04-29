import asyncio
import logging
from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.logs")

# ── The shared queue ──────────────────────────────────────────
# Each item is a plain dict matching the logs_request_log columns.
# Unbounded queue — the worker drains it continuously.
_queue: asyncio.Queue = asyncio.Queue()


def enqueue(entry: dict) -> None:
    """
    Non-blocking: put a log entry onto the queue.
    Called from the middleware — never awaited, never blocks the request.
    """
    try:
        _queue.put_nowait(entry)
    except Exception:
        # Should never happen with an unbounded queue, but never crash a request
        logger.warning("log queue put_nowait failed — entry dropped")


async def _write_batch(batch: list[dict]) -> None:
    """Insert a batch of log rows into logs_request_log."""
    if not batch:
        return
    try:
        db = get_client()
        db.table("logs_request_log").insert(batch).execute()
        logger.debug("log_worker | wrote %d row(s)", len(batch))
    except Exception as exc:
        logger.error("log_worker | DB write failed: %s", exc)


async def log_worker() -> None:
    """
    Background asyncio task — started at app startup, stopped at shutdown.

    Strategy:
    - Block-wait for the first item (no busy-loop).
    - Drain up to BATCH_SIZE additional items that are already queued.
    - Write the whole batch in one Supabase insert call.
    - Repeat.
    """
    BATCH_SIZE = 50
    logger.info("log_worker started")

    while True:
        try:
            # Block until at least one entry arrives
            first = await _queue.get()
            batch = [first]

            # Drain whatever is already in the queue (up to BATCH_SIZE - 1 more)
            while len(batch) < BATCH_SIZE:
                try:
                    batch.append(_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            await _write_batch(batch)

            # Mark each item done
            for _ in batch:
                _queue.task_done()

        except asyncio.CancelledError:
            # Shutdown signal — drain whatever remains before exiting
            logger.info("log_worker shutting down, draining %d remaining entries…", _queue.qsize())
            remaining: list[dict] = []
            while not _queue.empty():
                try:
                    remaining.append(_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            await _write_batch(remaining)
            logger.info("log_worker stopped")
            return

        except Exception as exc:
            # Never crash the worker — log and keep going
            logger.error("log_worker unexpected error: %s", exc, exc_info=True)
