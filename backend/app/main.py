from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db.database import init_db
from .api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# StaticFiles checks the directory exists at construction time (module import,
# before lifespan runs) -- must create it here, not inside lifespan.
Path(settings.generated_dir, "images").mkdir(parents=True, exist_ok=True)

app = FastAPI(title="LinkedIn Content Agent", lifespan=lifespan)
app.include_router(router)
app.mount("/generated", StaticFiles(directory=settings.generated_dir), name="generated")
