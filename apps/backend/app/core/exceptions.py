"""Custom exception classes and global error handlers."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette import status


class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found error."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message=message, status_code=status.HTTP_404_NOT_FOUND)


class UnauthorizedError(AppError):
    """Authentication error."""

    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message=message, status_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(AppError):
    """Authorization error."""

    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message=message, status_code=status.HTTP_403_FORBIDDEN)


class ValidationError(AppError):
    """Validation error."""

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class ConflictError(AppError):
    """Conflict error (e.g., trying to modify an ended resource)."""

    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class MessageTooLargeError(AppError):
    """Raised when a user-supplied message body exceeds the server cap.

    Maps to HTTP 413 Payload Too Large.

    Motivation: Prevents iOS clients from being forced to JSON-decode
    arbitrarily-large message bodies, which can OOM/crash older devices.
    Assistant-side messages take a different path (truncation with sentinel)
    so the conversation remains usable even when the model emits a very
    long response.
    """

    def __init__(
        self,
        message: str = "Message content exceeds maximum allowed size",
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        _request: Request,
        _exc: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )
