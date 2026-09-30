"""Cloud-ready assignment portal; local SQLite and private disk storage by default."""
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
import os
import secrets
import uuid

from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from cloud_storage import delete_object, open_download, save_upload, using_s3

load_dotenv()
db = SQLAlchemy()
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "zip", "png", "jpg", "jpeg"}


def utcnow():
    return datetime.now(timezone.utc)


def as_utc(value):
    """SQLite may return naive timestamps; interpret stored timestamps as UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    deadline = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    max_marks = db.Column(db.Integer, nullable=False)
    allowed_types = db.Column(db.String(255), nullable=False, default="pdf,doc,docx,txt,zip")
    max_file_mb = db.Column(db.Integer, nullable=False, default=16)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    file_name = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(255), nullable=False, unique=True)
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    status = db.Column(db.String(20), nullable=False, default="SUBMITTED", index=True)
    marks = db.Column(db.Integer)
    feedback = db.Column(db.Text)
    graded_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (db.UniqueConstraint("assignment_id", "student_id", name="one_submission_per_student_assignment"),)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-this-secret"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///portal.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=os.getenv("UPLOAD_FOLDER", str(Path(app.instance_path) / "uploads")),
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)),
        ALLOW_LATE_SUBMISSIONS=os.getenv("ALLOW_LATE_SUBMISSIONS", "true").lower() == "true",
        RESUBMISSIONS_ALLOWED=os.getenv("RESUBMISSIONS_ALLOWED", "true").lower() == "true",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    Limiter(get_remote_address, app=app, default_limits=["300 per hour"],
            storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"))

    with app.app_context():
        db.create_all()
        bootstrap_email = os.getenv("BOOTSTRAP_TEACHER_EMAIL")
        bootstrap_password = os.getenv("BOOTSTRAP_TEACHER_PASSWORD")
        if bootstrap_email and bootstrap_password and not User.query.filter_by(email=bootstrap_email.lower()).first():
            db.session.add(User(name="Demo Teacher", email=bootstrap_email.lower(), role="teacher",
                                password_hash=generate_password_hash(bootstrap_password)))
            db.session.commit()

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                if request.path.startswith("/api/"):
                    return jsonify(error="Authentication required"), 401
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def roles(*allowed):
        def decorator(view):
            @wraps(view)
            @login_required
            def wrapped(*args, **kwargs):
                user = db.session.get(User, session.get("user_id"))
                if not user or user.role not in allowed:
                    if request.path.startswith("/api/"):
                        return jsonify(error="Forbidden"), 403
                    abort(403)
                return view(*args, **kwargs)
            return wrapped
        return decorator

    def current_user():
        user_id = session.get("user_id")
        return db.session.get(User, user_id) if user_id else None

    @app.before_request
    def protect_authenticated_posts():
        if request.method == "POST" and session.get("user_id") and request.endpoint != "login":
            sent = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
            if not session.get("csrf_token") or not secrets.compare_digest(sent, session["csrf_token"]):
                abort(400, "Invalid CSRF token")

    def owns_course(course_id, teacher_id):
        return Course.query.filter_by(id=course_id, teacher_id=teacher_id).first()

    @app.context_processor
    def inject_user():
        return {"current_user": current_user()}

    @app.get("/")
    def home():
        return redirect(url_for("dashboard")) if session.get("user_id") else redirect(url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name, email, password = request.form.get("name", "").strip(), request.form.get("email", "").strip().lower(), request.form.get("password", "")
            if not name or len(name) > 120 or "@" not in email or len(password) < 10:
                flash("Enter a name, valid email, and password with at least 10 characters.", "error")
            elif User.query.filter_by(email=email).first():
                flash("That email is already registered.", "error")
            else:
                db.session.add(User(name=name, email=email, role="student", password_hash=generate_password_hash(password)))
                db.session.commit()
                flash("Account created. Sign in to continue.", "success")
                return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            # Permit account switching and ensure a failed re-login cannot retain an old identity.
            session.clear()
            email = request.form.get("email", "").strip().lower()
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, request.form.get("password", "")):
                session["user_id"] = user.id
                session["csrf_token"] = secrets.token_urlsafe(32)
                return redirect(url_for("dashboard"))
            flash("Invalid email or password.", "error")
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        user = current_user()
        if user.role == "teacher":
            courses = Course.query.filter_by(teacher_id=user.id).all()
            assignments = Assignment.query.filter(Assignment.course_id.in_([c.id for c in courses])).all() if courses else []
            ids = [a.id for a in assignments]
            subs = Submission.query.filter(Submission.assignment_id.in_(ids)).order_by(Submission.submitted_at.desc()).all() if ids else []
            return render_template("teacher.html", courses=courses, assignments=assignments, submissions=subs)
        assignments = Assignment.query.order_by(Assignment.deadline).all()
        my_subs = Submission.query.filter_by(student_id=user.id).all()
        by_assignment = {s.assignment_id: s for s in my_subs}
        return render_template("student.html", assignments=assignments, by_assignment=by_assignment,
                               pending=sum(a.id not in by_assignment for a in assignments),
                               late=sum(s.status == "LATE" for s in my_subs), graded=sum(s.status == "GRADED" for s in my_subs))

    @app.post("/courses")
    @roles("teacher")
    def create_course():
        name = request.form.get("name", "").strip()
        if not name or len(name) > 160:
            flash("Course name is required (160 characters maximum).", "error")
        else:
            db.session.add(Course(name=name, teacher_id=current_user().id))
            db.session.commit()
            flash("Course created.", "success")
        return redirect(url_for("dashboard"))

    @app.post("/assignments")
    @roles("teacher")
    def create_assignment():
        try:
            course_id = int(request.form.get("course_id", ""))
            deadline = datetime.fromisoformat(request.form.get("deadline", "").replace("Z", "+00:00"))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            max_marks = int(request.form.get("max_marks", ""))
            max_file_mb = int(request.form.get("max_file_mb", "16"))
            title = request.form.get("title", "").strip()
            allowed = ",".join(x.strip().lower().lstrip(".") for x in request.form.get("allowed_types", "pdf,doc,docx,txt,zip").split(",") if x.strip())
            if not owns_course(course_id, current_user().id) or not title or len(title) > 180 or max_marks < 1 or not 1 <= max_file_mb <= 100 or not allowed:
                raise ValueError
            db.session.add(Assignment(course_id=course_id, title=title, description=request.form.get("description", ""), deadline=deadline,
                                      max_marks=max_marks, max_file_mb=max_file_mb, allowed_types=allowed, created_by=current_user().id))
            db.session.commit()
            flash("Assignment created.", "success")
        except (ValueError, TypeError):
            db.session.rollback()
            flash("Check course, title, deadline, file size, and marks.", "error")
        return redirect(url_for("dashboard"))

    @app.post("/assignments/<int:assignment_id>/delete")
    @roles("teacher")
    def delete_assignment(assignment_id):
        assignment = db.session.get(Assignment, assignment_id)
        if not assignment or not owns_course(assignment.course_id, current_user().id):
            abort(404)
        if Submission.query.filter_by(assignment_id=assignment.id).first():
            flash("Assignments with submissions cannot be deleted.", "error")
        else:
            db.session.delete(assignment)
            db.session.commit()
            flash("Assignment deleted.", "success")
        return redirect(url_for("dashboard"))

    @app.post("/assignments/<int:assignment_id>/submit")
    @roles("student")
    def submit_assignment(assignment_id):
        assignment = db.session.get(Assignment, assignment_id)
        if not assignment:
            abort(404)
        if not app.config["ALLOW_LATE_SUBMISSIONS"] and utcnow() > as_utc(assignment.deadline):
            flash("The deadline has passed.", "error")
            return redirect(url_for("dashboard"))
        existing = Submission.query.filter_by(assignment_id=assignment.id, student_id=current_user().id).first()
        if existing and (not app.config["RESUBMISSIONS_ALLOWED"] or existing.status == "GRADED"):
            flash("Resubmission is not allowed for this assignment.", "error")
            return redirect(url_for("dashboard"))
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            flash("Choose a file to upload.", "error")
            return redirect(url_for("dashboard"))
        original_name = secure_filename(uploaded.filename)
        extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
        if extension not in set(assignment.allowed_types.lower().split(",")):
            flash("This file type is not allowed.", "error")
            return redirect(url_for("dashboard"))
        uploaded.stream.seek(0, os.SEEK_END)
        size = uploaded.stream.tell()
        uploaded.stream.seek(0)
        limit = min(assignment.max_file_mb * 1024 * 1024, app.config["MAX_CONTENT_LENGTH"])
        if size > limit:
            flash(f"File is too large (maximum {limit // (1024 * 1024)} MB).", "error")
            return redirect(url_for("dashboard"))
        now = utcnow()
        key = f"{assignment.id}/{current_user().id}/{uuid.uuid4().hex}.{extension}"
        try:
            save_upload(uploaded, key, app.config["UPLOAD_FOLDER"])
            status = "LATE" if now > as_utc(assignment.deadline) else "SUBMITTED"
            if existing:
                old_key = existing.storage_key
                existing.file_name, existing.storage_key = original_name, key
                existing.submitted_at, existing.status = now, status
                existing.marks, existing.feedback, existing.graded_at = None, None, None
                db.session.commit()
                delete_object(old_key, app.config["UPLOAD_FOLDER"])
            else:
                db.session.add(Submission(assignment_id=assignment.id, student_id=current_user().id, file_name=original_name,
                                          storage_key=key, submitted_at=now, status=status))
                db.session.commit()
        except Exception:
            db.session.rollback()
            delete_object(key, app.config["UPLOAD_FOLDER"])
            raise
        flash(f"Submission received ({status.lower()}).", "success")
        return redirect(url_for("dashboard"))

    @app.post("/submissions/<int:submission_id>/grade")
    @roles("teacher")
    def grade_submission(submission_id):
        sub = db.session.get(Submission, submission_id)
        assignment = db.session.get(Assignment, sub.assignment_id) if sub else None
        if not sub or not assignment or not owns_course(assignment.course_id, current_user().id):
            abort(404)
        try:
            marks = int(request.form.get("marks", ""))
            feedback = request.form.get("feedback", "").strip()
            if marks < 0 or marks > assignment.max_marks or len(feedback) > 5000:
                raise ValueError
        except ValueError:
            flash(f"Marks must be between 0 and {assignment.max_marks}; feedback is limited to 5000 characters.", "error")
            return redirect(url_for("dashboard"))
        sub.marks, sub.feedback, sub.graded_at, sub.status = marks, feedback, utcnow(), "GRADED"
        db.session.commit()
        flash("Grade saved.", "success")
        return redirect(url_for("dashboard"))

    @app.get("/submissions/<int:submission_id>/download")
    @login_required
    def download_submission(submission_id):
        sub = db.session.get(Submission, submission_id)
        if not sub:
            abort(404)
        user = current_user()
        assignment = db.session.get(Assignment, sub.assignment_id)
        if user.role == "student" and sub.student_id != user.id:
            abort(403)
        if user.role == "teacher" and not owns_course(assignment.course_id, user.id):
            abort(403)
        stored = open_download(sub.storage_key, app.config["UPLOAD_FOLDER"])
        if using_s3():
            from flask import Response
            return Response(stored, mimetype="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{secure_filename(sub.file_name)}"', "Cache-Control": "private, no-store"})
        if not stored.is_file():
            abort(404)
        return send_file(stored, as_attachment=True, download_name=sub.file_name, max_age=0)

    @app.get("/api/assignments")
    @login_required
    def api_assignments():
        rows = Assignment.query.order_by(Assignment.deadline).all()
        return jsonify([{ "id": a.id, "course_id": a.course_id, "title": a.title, "description": a.description,
                          "deadline": a.deadline.isoformat(), "max_marks": a.max_marks } for a in rows])

    @app.errorhandler(413)
    def too_large(_error):
        flash("Upload exceeds the server upload limit.", "error")
        return redirect(url_for("dashboard")) if session.get("user_id") else ("Upload too large", 413)

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403, message="You do not have access to this resource."), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="The requested resource was not found."), 404

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
