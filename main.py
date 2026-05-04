from dotenv import load_dotenv
load_dotenv()  # must be first — services read env vars at import time

import asyncio
import time
import logging
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from app.v1 import onboarding, auth, staff, master, iam, bilty_setting, bilty, challan, fleet, ewaybill
from app.services.logs.service import enqueue, log_worker
from app.services.ewaybill.token_service import load_jwt_token

# ── Logging setup ─────────────────────────────────────────────
# stream=sys.stdout ensures logs appear immediately in Coolify
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
    force=True,   # override any previously set handlers (e.g. from gunicorn)
)

# Pipe uvicorn & gunicorn internal logs through the same handler
for _name in ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn", "gunicorn.error", "gunicorn.access"):
    logging.getLogger(_name).handlers = []
    logging.getLogger(_name).propagate = True

logger = logging.getLogger("movesure")

# ── Lifespan: start/stop background log worker ────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(log_worker())
    logger.info("Background log worker started")

    # ── E-Way Bill: ensure Masters India token is live on startup ─────────
    try:
        token = load_jwt_token()
        if token:
            logger.info("Masters India JWT token is valid and ready")
        else:
            logger.warning("Masters India JWT token could not be obtained on startup")
    except Exception as _ewb_exc:
        logger.warning("Masters India token check failed on startup: %s", _ewb_exc)

    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        logger.info("Background log worker stopped")

app = FastAPI(
    title="MoveSure API",
    version="1.0.0",
    description="MoveSure Backend — Logistics Management Platform",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
# Add origins your frontend runs on. Adjust before going to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Sensitive fields stripped from logged request bodies ──────
_REDACT = {"password", "token", "secret", "access_token", "refresh_token"}


# ── Client type detection ─────────────────────────────────────
def _detect_client(user_agent: str | None) -> str:
    """Classify the HTTP client from its User-Agent string."""
    if not user_agent:
        return "unknown"
    ua = user_agent.lower()
    if "postman" in ua:
        return "postman"
    if "insomnia" in ua:
        return "insomnia"
    if "powershell" in ua or "invoke-webrequest" in ua:
        return "powershell"
    if "curl" in ua:
        return "curl"
    if "python-httpx" in ua or "httpx" in ua:
        return "python_httpx"
    if "python-requests" in ua or "requests" in ua:
        return "python_requests"
    if "aiohttp" in ua:
        return "python_aiohttp"
    if "python" in ua:
        return "python_client"
    if "okhttp" in ua or "retrofit" in ua:
        return "android_client"
    if "cfnetwork" in ua or "darwin" in ua:
        return "ios_client"
    if "android" in ua:
        return "android_browser"
    if "iphone" in ua or "ipad" in ua:
        return "ios_browser"
    if "mozilla" in ua and ("chrome" in ua or "crios" in ua):
        return "browser_chrome"
    if "mozilla" in ua and "firefox" in ua:
        return "browser_firefox"
    if "mozilla" in ua and "safari" in ua:
        return "browser_safari"
    if "mozilla" in ua and "edg" in ua:
        return "browser_edge"
    if "mozilla" in ua:
        return "browser"
    return "api_client"


def _sanitize(obj, depth: int = 0):
    """Recursively redact sensitive keys from a dict/list before logging."""
    if depth > 5 or obj is None:
        return obj
    if isinstance(obj, dict):
        return {
            k: "***" if k.lower() in _REDACT else _sanitize(v, depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_sanitize(i, depth + 1) for i in obj]
    return obj


# ── Request/Response middleware ───────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    correlation_id = str(uuid.uuid4())

    # Read and cache request body
    body_bytes = await request.body()
    try:
        body_parsed = json.loads(body_bytes) if body_bytes else None
    except Exception:
        body_parsed = body_bytes.decode("utf-8", errors="replace") if body_bytes else None

    body_safe = _sanitize(body_parsed)

    logger.info(
        "→ [%s] %s %s | client: %s | body: %s",
        correlation_id[:8],
        request.method,
        request.url.path,
        _detect_client(request.headers.get("user-agent")),
        json.dumps(body_safe, default=str) if body_safe is not None else "<empty>",
    )

    # Replay body so route handler can still read it
    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    status_code = 500
    error_message = None
    resp_log = None
    resp_body = b""

    try:
        response = await call_next(Request(request.scope, receive))
        status_code = response.status_code

        resp_chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            resp_chunks.append(chunk)
        resp_body = b"".join(resp_chunks)

        # Only parse JSON for logging; leave other content types untouched
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                resp_log = json.loads(resp_body)
            except Exception:
                resp_log = None
        else:
            resp_log = None  # HTML/static — don't parse, don't log body

    except Exception as exc:
        error_message = str(exc)
        logger.error(
            "← [%s] %s %s | UNHANDLED EXCEPTION | %s",
            correlation_id[:8],
            request.method,
            request.url.path,
            error_message,
            exc_info=True,
        )
        raise
    finally:
        elapsed_ms = int((time.time() - start) * 1000)

        logger.info(
            "← [%s] %s %s | status: %d | %d ms | response: %s",
            correlation_id[:8],
            request.method,
            request.url.path,
            status_code,
            elapsed_ms,
            json.dumps(resp_log, default=str)[:500] if resp_log is not None else "<non-json>",
        )

        # Extract user context:
        #  - authenticated endpoints: JWT middleware sets request.state.user  (keys: sub, session_id, ...)
        #  - login endpoint:          route sets request.state.log_user       (keys: id, session_id, ...)
        jwt_ctx: dict  = getattr(request.state, "user", {}) or {}
        post_ctx: dict = getattr(request.state, "log_user", {}) or {}
        user_ctx = jwt_ctx or post_ctx

        # Normalise user_id key: JWT uses 'sub', login route uses 'id'
        user_id = user_ctx.get("sub") or user_ctx.get("id")

        raw_ua = request.headers.get("user-agent")
        client_type = _detect_client(raw_ua)

        # Build the log entry and push to the background queue — fire and forget
        enqueue({
            "user_id":       user_id,
            "session_id":    user_ctx.get("session_id"),
            "company_id":    user_ctx.get("company_id"),
            "branch_id":     user_ctx.get("branch_id"),
            "method":        request.method,
            "path":          request.url.path,
            "query_params":  dict(request.query_params) or {},
            "request_body":  body_safe,
            "status_code":   status_code,
            "error_message": error_message,
            "ip_address":    request.client.host if request.client else None,
            "user_agent":    raw_ua,
            "client_type":   client_type,
            "duration_ms":   elapsed_ms,
            "correlation_id": correlation_id,
        })

    # Return raw bytes for non-JSON responses (HTML docs, static files, etc.)
    # Strip hop-by-hop / size headers — we've buffered the body so they're stale
    _HOP_BY_HOP = {"content-length", "transfer-encoding", "connection", "keep-alive"}
    forwarded_headers = {
        k: v for k, v in response.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return JSONResponse(
            content=resp_log,
            status_code=status_code,
            headers=forwarded_headers,
        )
    return Response(
        content=resp_body,
        status_code=status_code,
        headers=forwarded_headers,
        media_type=response.media_type,
    )


# ── Routers ───────────────────────────────────────────────────
app.include_router(onboarding.router, prefix="/v1")
app.include_router(auth.router, prefix="/v1")
app.include_router(staff.router, prefix="/v1")
app.include_router(master.router, prefix="/v1")
app.include_router(iam.router, prefix="/v1")
app.include_router(bilty_setting.router, prefix="/v1")
app.include_router(bilty.router, prefix="/v1")
app.include_router(challan.router, prefix="/v1")
app.include_router(fleet.router, prefix="/v1")
app.include_router(ewaybill.router, prefix="/v1")


# ── Root + Health check ───────────────────────────────────────
@app.get("/", tags=["System"])
def root():
    return {"status": "ok", "service": "MoveSure API", "version": "1.0.0"}


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
