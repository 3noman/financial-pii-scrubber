from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
import time
from app.api.routes import analysis, chat, statements
from app.config import get_settings
from app.core.exceptions import ScrubberBaseException
from app.core.logging import get_logger
from app.database.connection import init_db
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = get_logger(__name__)
settings = get_settings()
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Simple sliding-window rate limiter store (IP -> list of request timestamps)
_RATE_LIMIT_STORE: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60.0


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
  try:
    init_db()
    logger.info("Database schema verified on startup.")
  except Exception as exc:
    logger.warning(
        f"Database connection not ready at startup ({type(exc).__name__}). "
        "Ensure PostgreSQL is running."
    )
  yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "Privacy-first financial statement PII scrubber and grounded AI budget"
        " analyzer."
    ),
    lifespan=lifespan,
)

# Restrict CORS to configured frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def security_headers_and_rate_limit_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
  client_ip = request.client.host if request.client else "local"
  now = time.time()

  # Apply rate limiting to mutation/expensive endpoints
  if request.method == "POST" and request.url.path.startswith("/api/"):
    timestamps = [
        t
        for t in _RATE_LIMIT_STORE[client_ip]
        if now - t < RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
      return JSONResponse(
          status_code=429,
          content={
              "detail": (
                  "Too many requests. Please wait a moment and try again."
              )
          },
      )
    timestamps.append(now)
    _RATE_LIMIT_STORE[client_ip] = timestamps

  response = await call_next(request)
  # Security HTTP headers
  response.headers["X-Content-Type-Options"] = "nosniff"
  response.headers["X-Frame-Options"] = "DENY"
  response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
  response.headers["X-XSS-Protection"] = "1; mode=block"
  return response


@app.exception_handler(ScrubberBaseException)
async def handle_scrubber_exception(
    request: Request, exc: ScrubberBaseException
) -> JSONResponse:
  """Returns human-centered, PII-free error messages for known application exceptions."""
  return JSONResponse(
      status_code=exc.status_code,
      content={"detail": exc.user_message},
  )


# Register API Routers
app.include_router(statements.router)
app.include_router(analysis.router)
app.include_router(chat.router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
  return {"status": "ok", "app": settings.APP_NAME}


# Mount static frontend assets
if (FRONTEND_DIR / "css").exists():
  app.mount(
      "/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css"
  )
if (FRONTEND_DIR / "js").exists():
  app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")


@app.get("/")
def serve_dashboard():  # type: ignore[no-untyped-def]
  index_file = FRONTEND_DIR / "index.html"
  if index_file.exists():
    return FileResponse(str(index_file))
  return {"message": "Financial Data Privacy Scrubber API is running."}