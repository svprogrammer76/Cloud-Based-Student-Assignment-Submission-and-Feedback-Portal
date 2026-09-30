from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from hashlib import sha256
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from google.api_core.exceptions import NotFound

from app.config import settings
from app.models.schemas import GradeInput
from app.services.auth import current_user, require_role
from app.services.firebase import get_db
from app.services.object_storage import delete_object, read_object, save_object

router = APIRouter(prefix="/api", tags=["submissions and grading"])
ALLOWED = {"pdf", "doc", "docx", "txt", "zip", "png", "jpg", "jpeg"}


def _assignment(assignment_id):
    snap = get_db().collection("assignments").document(assignment_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return snap.to_dict()


def _teacher_assignment(assignment_id, uid):
    item = _assignment(assignment_id)
    course = get_db().collection("courses").document(item["courseId"]).get()
    if not course.exists or course.to_dict().get("teacherId") != uid:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return item


@router.post("/assignments/{assignment_id}/submit", status_code=201)
async def submit(assignment_id: str, file: UploadFile = File(...), user=Depends(require_role("student"))):
    assignment = _assignment(assignment_id)
    data = await file.read(settings.max_upload_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Choose a non-empty file")
    extension = Path(file.filename or "").suffix.lower().lstrip(".")
    allowed = set(assignment.get("allowedTypes", [])) & ALLOWED
    max_bytes = min(assignment.get("maxFileSizeMB", 16) * 1024 * 1024, settings.max_upload_bytes)
    if extension not in allowed:
        raise HTTPException(status_code=415, detail="This file type is not allowed")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the assignment size limit")
    now = datetime.now(timezone.utc)
    due = datetime.fromisoformat(assignment["dueAt"].replace("Z", "+00:00"))
    if not settings.allow_late_submissions and now > due:
        raise HTTPException(status_code=409, detail="The assignment deadline has passed")
    db = get_db()
    prior = list(db.collection("submissions").where("assignmentId", "==", assignment_id).where("studentUid", "==", user["uid"]).stream())
    if prior and (not settings.allow_resubmissions or not assignment.get("allowResubmission", True)):
        raise HTTPException(status_code=409, detail="Resubmission is disabled")
    if any(s.to_dict().get("status") == "GRADED" for s in prior):
        raise HTTPException(status_code=409, detail="A graded submission cannot be replaced")
    counter_id = sha256(f"{assignment_id}:{user['uid']}".encode()).hexdigest()
    counter_ref = db.collection("submissionCounters").document(counter_id)
    submission_id = str(uuid4())
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename or "upload").name)[:180] or "upload"
    object_path = f"assignments/{assignment_id}/{user['uid']}/{submission_id}/{filename}"
    try:
        save_object(object_path, data, file.content_type or "application/octet-stream")
        row = {"assignmentId": assignment_id, "courseId": assignment["courseId"], "studentUid": user["uid"],
               "studentName": user["name"], "fileName": filename, "storagePath": object_path, "size": len(data),
               "mime": file.content_type or "application/octet-stream", "submittedAt": now.isoformat(),
               "version": 0, "late": now > due, "status": "LATE" if now > due else "SUBMITTED",
               "marks": None, "feedback": None, "gradedAt": None}
        from google.cloud import firestore
        transaction = db.transaction()

        @firestore.transactional
        def save_submission(tx):
            counter = counter_ref.get(transaction=tx)
            version = (counter.to_dict() or {}).get("version", 0) + 1 if counter.exists else 1
            row["version"] = version
            tx.set(counter_ref, {"version": version, "assignmentId": assignment_id, "studentUid": user["uid"]})
            tx.set(db.collection("submissions").document(submission_id), row)

        save_submission(transaction)
    except Exception:
        try:
            delete_object(object_path)
        except Exception:
            # Keep the original failure; an operator can reconcile a possible orphan object.
            pass
        raise
    return {"id": submission_id, **row}


@router.get("/submissions/me")
def my_submissions(user=Depends(require_role("student"))):
    docs = get_db().collection("submissions").where("studentUid", "==", user["uid"]).stream()
    rows = [{"id": d.id, **d.to_dict()} for d in docs]
    return sorted(rows, key=lambda row: row.get("submittedAt", ""), reverse=True)


@router.get("/teacher/submissions")
def teacher_submissions(user=Depends(require_role("teacher"))):
    db = get_db()
    owned_ids = {d.id for d in db.collection("assignments").where("createdBy", "==", user["uid"]).stream()}
    rows = []
    for assignment_id in owned_ids:
        rows.extend({"id": d.id, **d.to_dict()} for d in db.collection("submissions").where("assignmentId", "==", assignment_id).stream())
    return sorted(rows, key=lambda row: row.get("submittedAt", ""), reverse=True)


@router.get("/assignments/{assignment_id}/submissions")
def assignment_submissions(assignment_id: str, user=Depends(require_role("teacher"))):
    _teacher_assignment(assignment_id, user["uid"])
    docs = get_db().collection("submissions").where("assignmentId", "==", assignment_id).stream()
    rows = [{"id": d.id, **d.to_dict()} for d in docs]
    return sorted(rows, key=lambda row: row.get("submittedAt", ""), reverse=True)


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: str, user=Depends(current_user)):
    snap = get_db().collection("submissions").document(submission_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Submission not found")
    row = snap.to_dict()
    if user["role"] == "student" and row.get("studentUid") != user["uid"]:
        raise HTTPException(status_code=404, detail="Submission not found")
    if user["role"] == "teacher":
        _teacher_assignment(row["assignmentId"], user["uid"])
    return {"id": snap.id, **row}


@router.get("/submissions/{submission_id}/feedback")
def feedback(submission_id: str, user=Depends(require_role("student"))):
    return get_submission(submission_id, user)


@router.post("/submissions/{submission_id}/grade")
def grade(submission_id: str, data: GradeInput, user=Depends(require_role("teacher"))):
    db = get_db()
    ref = db.collection("submissions").document(submission_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub = snap.to_dict()
    assignment = _teacher_assignment(sub["assignmentId"], user["uid"])
    if data.marks > assignment["maxMarks"]:
        raise HTTPException(status_code=422, detail=f"Marks cannot exceed {assignment['maxMarks']}")
    changes = {"marks": data.marks, "feedback": data.feedback, "gradedAt": datetime.now(timezone.utc).isoformat(), "status": "GRADED"}
    ref.update(changes)
    return {"id": submission_id, **sub, **changes}


@router.get("/submissions/{submission_id}/download")
def download_submission(submission_id: str, user=Depends(current_user)):
    snap = get_db().collection("submissions").document(submission_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Submission not found")
    row = snap.to_dict()
    if user["role"] == "student" and row.get("studentUid") != user["uid"]:
        raise HTTPException(status_code=404, detail="Submission not found")
    if user["role"] == "teacher":
        _teacher_assignment(row["assignmentId"], user["uid"])
    try:
        content = read_object(row["storagePath"])
    except NotFound:
        raise HTTPException(status_code=404, detail="Stored file is missing")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Stored file is missing")
    return Response(content, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{row["fileName"]}"', "Cache-Control": "private, no-store"})
