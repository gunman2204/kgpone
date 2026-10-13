from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi.responses import JSONResponse
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from src.api.exceptions.handlers import (
    http_exception_handler, validation_exception_handler, 
    generic_exception_handler, value_error_handler, 
    integrity_error_handler
)
from src.api.exceptions.openapi import customize_openapi
from sqlalchemy.exc import IntegrityError

# Load environment variables from .env file before importing local modules
load_dotenv()
from src.api.routes import user_routes, academic_routes, document_routes, query_routes, chat_routes, system_routes
from src.api.middleware.security_middleware import SecurityHeadersMiddleware
from src.api.middleware.request_logger import RequestLoggerMiddleware
from src.config.settings import Settings

from contextlib import asynccontextmanager
from src.infrastructure.database import Base, engine
from src.workers.watcher_manager import watcher_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.infrastructure.database import init_local_db
    init_local_db()
    watcher_manager.start()
    yield
    watcher_manager.stop()

app = FastAPI(title="KgpOne Backend API", lifespan=lifespan)
customize_openapi(app)

# Database tables are now managed by Alembic migrations
# Base.metadata.create_all(bind=engine)

# Setup CORS for the frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apply custom Security Headers (CSP, HSTS, etc.)
app.add_middleware(SecurityHeadersMiddleware)

# Apply Centralized Request Logging
app.add_middleware(RequestLoggerMiddleware)

# Apply Global Exception Handlers for Standard Responses
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(ValueError, value_error_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# RBAC Routers
app.include_router(user_routes.router, prefix="/api/v1")
app.include_router(academic_routes.router, prefix="/api/v1")
app.include_router(document_routes.router, prefix="/api/v1")
app.include_router(query_routes.router, prefix="/api/v1")
app.include_router(chat_routes.router) # chat_routes already has prefix /api/v1/chat
app.include_router(system_routes.router, prefix="/api/v1")

# ── MCP Server — mounted at /mcp for external AI agent access ─────────────────
# Connect from Claude Desktop, MCP Inspector, or any MCP client:
#   SSE URL: http://localhost:8000/mcp/sse
try:
    from src.mcp.server import mcp as kgpone_mcp
    mcp_app = kgpone_mcp.sse_app()
    app.mount("/mcp", mcp_app)
except Exception as _mcp_err:
    import logging
    logging.getLogger("main").warning(f"MCP server could not be mounted: {_mcp_err}")

@app.get("/")
def read_root():
    return {"message": "Welcome to KgpOne Secure API"}

@app.get("/api")
def read_api_root():
    return {"message": "Welcome to KgpOne Secure API"}

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "API is healthy"}
