"""Lazy Firebase Admin SDK clients; credentials come from Application Default Credentials."""
import json
import os
import firebase_admin
from firebase_admin import credentials
from google.auth.credentials import AnonymousCredentials
from firebase_admin import auth, firestore, storage

from app.config import settings


def _app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None
        if settings.firebase_storage_bucket:
            options = options or {}
            options["storageBucket"] = settings.firebase_storage_bucket
        if settings.firebase_service_account_json:
            credential = credentials.Certificate(json.loads(settings.firebase_service_account_json))
        elif settings.google_application_credentials:
            credential = credentials.Certificate(settings.google_application_credentials)
        elif os.getenv("FIRESTORE_EMULATOR_HOST") or os.getenv("FIREBASE_AUTH_EMULATOR_HOST"):
            credential = AnonymousCredentials()
        else:
            credential = None
        return firebase_admin.initialize_app(credential=credential, options=options)


def get_db():
    return firestore.client(app=_app())


def get_bucket():
    return storage.bucket(app=_app())


def verify_token(token: str):
    return auth.verify_id_token(token, app=_app(), check_revoked=True)
