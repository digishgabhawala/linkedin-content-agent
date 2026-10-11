from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import settings
from .db.database import init_db
from .services.llm_client import TaskQueueUnavailable


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# StaticFiles checks the directory exists at construction time (module import,
# before lifespan runs) -- must create it here, not inside lifespan.
Path(settings.generated_dir, "images").mkdir(parents=True, exist_ok=True)

app = FastAPI(title="LinkedIn Content Agent", lifespan=lifespan)
app.include_router(router)

# LLM calls run on the user's worker via the task-queue (llm_client.py); turn
# their failures into clear HTTP errors the UI shows as-is.
_TEXT_ERRORS = {TaskQueueUnavailable: 503}


def _text_error_handler(status: int):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": str(exc)})
    return handler


for _exc, _status in _TEXT_ERRORS.items():
    app.add_exception_handler(_exc, _text_error_handler(_status))
app.mount("/generated", StaticFiles(directory=settings.generated_dir), name="generated")
