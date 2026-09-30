from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends

from app.services.auth import current_user
from app.services.firebase import get_db

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("")
def profile(user=Depends(current_user)):
    return user


@router.put("")
def save_profile(data: ProfileInput, user=Depends(current_user)):
    db = get_db()
    ref = db.collection("users").document(user["uid"])
    old = ref.get().to_dict() or {}
    # A client may set a display name, but never its own role.
    row = {"name": data.name, "email": user["email"], "role": old.get("role", "student"),
           "createdAt": old.get("createdAt", datetime.now(timezone.utc).isoformat()),
           "updatedAt": datetime.now(timezone.utc).isoformat()}
    ref.set(row)
    return {**user, "name": data.name, "role": row["role"]}
