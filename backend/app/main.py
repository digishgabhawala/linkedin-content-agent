from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.routes import public_router, router
from .config import settings
from .db.database import init_db
from .services.llm_client import TaskQueueUnavailable


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_init_db:
        init_db()
    yield


app = FastAPI(title="LinkedIn Content Agent", lifespan=lifespan)
app.include_router(public_router)
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


APP_PATH = "/linkedin"


class _AppFiles(StaticFiles):
    """Static files, except an unknown page path serves the app itself, so a
    deep link or a refresh under /linkedin/ still loads the frontend."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("assets/"):
                raise
            return await super().get_response("index.html", scope)


async def _to_app(request):
    # A path-only Location: behind the parent site's rewrite, an absolute URL
    # would send the browser to this deployment's own hostname.
    return RedirectResponse(APP_PATH, status_code=308)


def mount_frontend(web: FastAPI, dist: str | Path) -> None:
    """Serve the built frontend under /linkedin after the API routes.
    Vercel's static step only sees files present before the build, so the
    app serves its own build output, like task-queue's admin page."""
    index = Path(dist, "index.html")
    if index.is_file():
        async def app_page(request):
            return FileResponse(index)

        web.add_route("/", _to_app, include_in_schema=False)
        # Served as-is, not redirected to /linkedin/: the parent site strips
        # trailing slashes, so that redirect would loop.
        web.add_route(APP_PATH, app_page, include_in_schema=False)
        web.mount(APP_PATH, _AppFiles(directory=dist, html=True), name="frontend")


mount_frontend(app, settings.frontend_dist)
