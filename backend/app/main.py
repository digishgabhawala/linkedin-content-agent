from contextlib import asynccontextmanager
from fastapi import FastAPI
from .db.database import init_db
from .api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="LinkedIn Content Agent", lifespan=lifespan)
app.include_router(router)
