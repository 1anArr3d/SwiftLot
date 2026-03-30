"""
Firebase Auth middleware.
Verifies Firebase ID tokens and extracts the user_id.
"""
import os
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Header, HTTPException, Depends
from dotenv import load_dotenv

load_dotenv()

_cred_path = os.path.join(os.path.dirname(__file__), os.getenv("FIREBASE_CREDENTIALS", ""))
ADMIN_UID = os.getenv("ADMIN_UID")

if not firebase_admin._apps:
    cred = credentials.Certificate(_cred_path)
    firebase_admin.initialize_app(cred)


def get_current_user(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split("Bearer ")[1]
    try:
        decoded = auth.verify_id_token(token)
        return decoded["uid"]
    except auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token expired")
    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


def require_admin(user_id: str = Depends(get_current_user)) -> str:
    if user_id != ADMIN_UID:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id
