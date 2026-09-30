from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends

from app.models.schemas import CourseCreate
from app.services.auth import current_user, require_role
from app.services.firebase import get_db

router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.get("")
def list_courses(user=Depends(current_user)):
    rows = [dict(id=d.id, **d.to_dict()) for d in get_db().collection("courses").stream()]
    return [c for c in rows if user["role"] != "teacher" or c.get("teacherId") == user["uid"]]


@router.post("", status_code=201)
def create_course(data: CourseCreate, user=Depends(require_role("teacher"))):
    ref = get_db().collection("courses").document(str(uuid4()))
    row = {**data.model_dump(), "teacherId": user["uid"], "createdAt": datetime.now(timezone.utc).isoformat()}
    ref.set(row)
    return {"id": ref.id, **row}
