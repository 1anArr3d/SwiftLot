from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config import ALLOWED_ORIGINS
from scheduler import create_scheduler
import scraper
import discovery

from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    scraper.init_db()
    discovery.init_db()

    scheduler = create_scheduler()
    scheduler.start()
    print("[scheduler] Started — jobs at 8am, 2pm, 10pm CT")

    yield

    scheduler.shutdown(wait=False)
    print("[scheduler] Stopped.")


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
