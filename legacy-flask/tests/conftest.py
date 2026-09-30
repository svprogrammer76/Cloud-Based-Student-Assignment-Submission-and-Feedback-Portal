import pytest
from app import create_app, db


@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "ALLOW_LATE_SUBMISSIONS": True,
        "RESUBMISSIONS_ALLOWED": True,
        "MAX_CONTENT_LENGTH": 1024 * 1024,
    })
    with application.app_context():
        db.drop_all()
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
