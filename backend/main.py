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
import feed_scraper as scraper

from routes import router
import auction_listener as listener
import asyncio

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    listener.set_event_loop(asyncio.get_running_loop())

    # Initial full scrape + subscribe
    def _startup():
        listener.sync_with_db()       # immediately subscribe with what's in DB
        scraper.scrape_all()          # populate vehicles + discover auctions
        listener.sync_with_db()       # pick up any newly discovered auctions
    threading.Thread(target=_startup, daemon=True).start()
    listener.start_watchdog(interval=30)
    listener.start_retry_checker()
    listener.start_reconciler(interval=600)
    listener.start_periodic_scraper(interval=7200)

    yield

    print("[app] Shutting down.")


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
