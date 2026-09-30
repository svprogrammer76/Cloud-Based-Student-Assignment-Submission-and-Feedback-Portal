from datetime import datetime, timedelta, timezone
from io import BytesIO

from app import Assignment, Course, Submission, User, db
from werkzeug.security import generate_password_hash


def make_user(app, name, email, role):
    with app.app_context():
        user = User(name=name, email=email, role=role, password_hash=generate_password_hash("long-test-password"))
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, email):
    return client.post("/login", data={"email": email, "password": "long-test-password"}, follow_redirects=True)


def csrf(client):
    with client.session_transaction() as session:
        return session.get("csrf_token", "")


def setup_assignment(app, teacher_id):
    with app.app_context():
        course = Course(name="Cloud Computing", teacher_id=teacher_id)
        db.session.add(course)
        db.session.flush()
        assignment = Assignment(course_id=course.id, title="Cloud design", description="Upload PDF", deadline=datetime.now(timezone.utc) + timedelta(days=2), max_marks=100, allowed_types="pdf", max_file_mb=1, created_by=teacher_id)
        db.session.add(assignment)
        db.session.commit()
        return assignment.id


def test_registration_and_invalid_login(client):
    response = client.post("/register", data={"name": "A Student", "email": "s@example.edu", "password": "long-password"}, follow_redirects=True)
    assert b"Account created" in response.data
    assert b"Invalid email or password" in client.post("/login", data={"email": "s@example.edu", "password": "wrong"}, follow_redirects=True).data


def test_teacher_assignment_and_student_submission_grade_download(app, client):
    teacher = make_user(app, "Teacher", "t@example.edu", "teacher")
    student = make_user(app, "Student", "s@example.edu", "student")
    assignment_id = setup_assignment(app, teacher)

    login(client, "s@example.edu")
    assert client.get("/api/assignments").status_code == 200
    assert client.post(f"/assignments/{assignment_id}/submit", data={"csrf_token": csrf(client), "file": (BytesIO(b"bad"), "not.exe")}, content_type="multipart/form-data").status_code == 302
    assert b"file type is not allowed" in client.get("/dashboard").data
    result = client.post(f"/assignments/{assignment_id}/submit", data={"csrf_token": csrf(client), "file": (BytesIO(b"sample pdf"), "work.pdf")}, content_type="multipart/form-data", follow_redirects=True)
    assert b"Submission received" in result.data
    with app.app_context():
        submission = Submission.query.one()
        submission_id = submission.id
    assert client.get(f"/submissions/{submission_id}/download").status_code == 200

    other_id = make_user(app, "Other", "other@example.edu", "student")
    login_response = login(client, "other@example.edu")
    assert login_response.status_code == 200
    with client.session_transaction() as current_session:
        assert current_session["user_id"] == other_id
    with app.app_context():
        assert db.session.get(Submission, submission_id).student_id == student
    assert client.get(f"/submissions/{submission_id}/download").status_code == 403

    login(client, "t@example.edu")
    invalid_grade = client.post(f"/submissions/{submission_id}/grade", data={"csrf_token": csrf(client), "marks": "101", "feedback": "Too high"}, follow_redirects=True)
    assert invalid_grade.status_code == 200
    assert b"Marks must be between" in invalid_grade.data
    client.post(f"/submissions/{submission_id}/grade", data={"csrf_token": csrf(client), "marks": "95", "feedback": "Excellent",}, follow_redirects=True)
    with app.app_context():
        sub = db.session.get(Submission, submission_id)
        assert sub.marks == 95 and sub.status == "GRADED"
    assert client.get(f"/submissions/{submission_id}/download").status_code == 200


def test_role_protection_and_csrf(app, client):
    make_user(app, "Student", "s@example.edu", "student")
    login(client, "s@example.edu")
    assert client.post("/courses", data={"name": "Nope", "csrf_token": csrf(client)}).status_code == 403
    assert client.post("/logout", data={}).status_code == 400
    assert client.post("/logout", data={"csrf_token": csrf(client)}).status_code == 302
    assert client.get("/dashboard").status_code == 302
