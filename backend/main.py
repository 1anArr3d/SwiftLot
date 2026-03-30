from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config import ALLOWED_ORIGINS
import threading
from db import init_db
from scheduler import create_scheduler
import historical_harvester as harvester

from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    threading.Thread(target=_seed_historical, daemon=True).start()

    scheduler = create_scheduler()
    scheduler.start()
    print("[scheduler] Started — jobs at 8am, 2pm, 10pm CT")

    yield

    scheduler.shutdown(wait=False)
    print("[scheduler] Stopped.")


def _seed_historical():
    harvester.seed_from_json()
    harvester.harvest_api()


app = FastAPI(title="SwiftLot API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
