from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import AssignmentCreate
from app.services.auth import current_user, require_role
from app.services.firebase import get_db

router = APIRouter(prefix="/api/assignments", tags=["assignments"])


def _owned_course(course_id, teacher_id):
    snap = get_db().collection("courses").document(course_id).get()
    if not snap.exists or snap.to_dict().get("teacherId") != teacher_id:
        raise HTTPException(status_code=404, detail="Course not found")


@router.get("")
def list_assignments(user=Depends(current_user)):
    rows = [dict(id=d.id, **d.to_dict()) for d in get_db().collection("assignments").stream()]
    return [a for a in rows if user["role"] != "teacher" or a.get("createdBy") == user["uid"]]


@router.post("", status_code=201)
def create_assignment(data: AssignmentCreate, user=Depends(require_role("teacher"))):
    _owned_course(data.courseId, user["uid"])
    ref = get_db().collection("assignments").document(str(uuid4()))
    row = {**data.model_dump(mode="json"), "createdBy": user["uid"], "createdAt": datetime.now(timezone.utc).isoformat()}
    ref.set(row)
    return {"id": ref.id, **row}


@router.get("/{assignment_id}")
def get_assignment(assignment_id: str, user=Depends(current_user)):
    snap = get_db().collection("assignments").document(assignment_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Assignment not found")
    row = snap.to_dict()
    if user["role"] == "teacher" and row.get("createdBy") != user["uid"]:
        raise HTTPException(status_code=403, detail="Assignment is outside your courses")
    return {"id": snap.id, **row}


@router.put("/{assignment_id}")
def update_assignment(assignment_id: str, data: AssignmentCreate, user=Depends(require_role("teacher"))):
    ref = get_db().collection("assignments").document(assignment_id)
    snap = ref.get()
    if not snap.exists or snap.to_dict().get("createdBy") != user["uid"]:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _owned_course(data.courseId, user["uid"])
    changes = data.model_dump(mode="json")
    ref.update(changes)
    return {"id": assignment_id, **snap.to_dict(), **changes}


@router.delete("/{assignment_id}", status_code=204)
def delete_assignment(assignment_id: str, user=Depends(require_role("teacher"))):
    db = get_db()
    ref = db.collection("assignments").document(assignment_id)
    snap = ref.get()
    if not snap.exists or snap.to_dict().get("createdBy") != user["uid"]:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if next(db.collection("submissions").where("assignmentId", "==", assignment_id).limit(1).stream(), None):
        raise HTTPException(status_code=409, detail="Cannot delete an assignment with submissions")
    ref.delete()
