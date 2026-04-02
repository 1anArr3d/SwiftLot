from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from config import ALLOWED_ORIGINS
import threading
from db import init_db
from scheduler import create_scheduler, scheduled_discovery_and_scrape
import historical_harvester as harvester

from routes import router
import rtdb_listener as listener

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    threading.Thread(target=_seed_historical, daemon=True).start()

    # Subscribe to auctions already in DB immediately
    threading.Thread(target=listener.sync_with_db, daemon=True).start()
    listener.start_watchdog(interval=30)
    # Run pipeline in background so DB is fresh after any restart
    threading.Thread(target=scheduled_discovery_and_scrape, daemon=True).start()

    scheduler = create_scheduler()
    scheduler.start()
    print("[scheduler] Started — jobs at 8am, 12pm, 4pm, 8pm, 12am CT")

    yield

    scheduler.shutdown(wait=False)
    print("[scheduler] Stopped.")


def _seed_historical():
    harvester.seed_from_json()
    harvester.harvest_api()


app = FastAPI(
    title="SwiftLot API",
    version="1.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schemes = schema.get("components", {}).get("securitySchemes", {})
    if schemes:
        schema["security"] = [{list(schemes.keys())[0]: []}]
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
