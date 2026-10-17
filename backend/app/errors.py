from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ReasonedHTTPException(HTTPException):
    """An HTTP error the UI acts on: body {"detail": ..., "reason": ...}."""

    def __init__(self, status_code: int, detail: str, reason: str):
        super().__init__(status_code, detail)
        self.reason = reason


async def reasoned_http_exception_handler(request: Request, exc: ReasonedHTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.detail, "reason": exc.reason})
