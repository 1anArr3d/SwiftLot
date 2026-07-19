import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://swiftlot:swiftlot@localhost:5432/swiftlot")
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
).split(",")

INSPECTION_STATES = [s.strip() for s in os.getenv("INSPECTION_STATES", "TX").split(",") if s.strip()]

# Autura session cookies — set from browser when scraping authenticated pages
AUTURA_COOKIES: dict = {}
_session = os.getenv("AUTURA_SESSION", "")
_account = os.getenv("AUTURA_ACCOUNT_ID", "")
if _session:
    AUTURA_COOKIES["user-session"] = _session
if _account:
    AUTURA_COOKIES["selected-account-id"] = _account
