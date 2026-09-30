from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.firebase import get_db, verify_token

bearer = HTTPBearer(auto_error=False)


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Sign in is required")
    try:
        claims = verify_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Your sign-in token is invalid or expired")
    uid = claims["uid"]
    snapshot = get_db().collection("users").document(uid).get()
    profile = snapshot.to_dict() if snapshot.exists else {}
    return {"uid": uid, "email": claims.get("email", ""), "name": profile.get("name", claims.get("name", "Student")),
            "role": profile.get("role", "student")}


def require_role(*roles):
    def dependency(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="This action is not permitted for your role")
        return user
    return dependency
