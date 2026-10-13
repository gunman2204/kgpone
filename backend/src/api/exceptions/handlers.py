from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from src.schemas.response_schema import StandardResponse

def _cors_headers(request: Request) -> dict:
    origin = request.headers.get("origin", "")
    allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    allow_origin = origin if origin in allowed_origins else "*"
    return {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    response = StandardResponse(
        status="error",
        message=str(exc.detail),
        data=None
    )
    return JSONResponse(status_code=exc.status_code, content=response.model_dump(), headers=_cors_headers(request))

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    response = StandardResponse(
        status="error",
        message="Validation error",
        data={"errors": exc.errors()}
    )
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=response.model_dump(), headers=_cors_headers(request))

async def generic_exception_handler(request: Request, exc: Exception):
    import logging
    logger = logging.getLogger(__name__)
    logger.exception(f"Unhandled Exception: {str(exc)}")
    response = StandardResponse(
        status="error",
        message=str(exc) or "An unexpected error occurred",
        data=None
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=response.model_dump(), headers=_cors_headers(request))

async def value_error_handler(request: Request, exc: ValueError):
    response = StandardResponse(
        status="error",
        message=str(exc),
        data=None
    )
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=response.model_dump(), headers=_cors_headers(request))

from sqlalchemy.exc import IntegrityError
async def integrity_error_handler(request: Request, exc: IntegrityError):
    response = StandardResponse(
        status="error",
        message="Database integrity error. The record might already exist or a constraint was violated.",
        data={"detail": str(exc.orig) if hasattr(exc, "orig") else str(exc)}
    )
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=response.model_dump(), headers=_cors_headers(request))
