"""Promote an existing Firebase Auth account to teacher using Admin credentials.

Run from backend: python -m app.scripts.promote_teacher teacher@example.edu
"""
import sys
from datetime import datetime, timezone

from firebase_admin import auth
from app.services.firebase import _app, get_db


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.scripts.promote_teacher EMAIL")
    _app()
    user = auth.get_user_by_email(sys.argv[1])
    ref = get_db().collection("users").document(user.uid)
    old = ref.get().to_dict() or {}
    ref.set({"name": old.get("name") or user.display_name or "Teacher", "email": user.email,
             "role": "teacher", "createdAt": old.get("createdAt", datetime.now(timezone.utc).isoformat())})
    print(f"Promoted {user.email} ({user.uid}) to teacher")


if __name__ == "__main__":
    main()
