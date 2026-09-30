from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.middleware.request_id import RequestIdMiddleware
from app.routes import assignments, courses, profile, submissions

app = FastAPI(title="Cloud Assignment Portal API", version="1.0.0", description="Firebase-authenticated assignment portal REST API")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.allowed_origins.split(",")],
                   allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])
app.add_middleware(RequestIdMiddleware)
app.include_router(profile.router)
app.include_router(courses.router)
app.include_router(assignments.router)
app.include_router(submissions.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# On the free Render deployment, serve the built React app and API from one origin.
# Locally Vite remains a separate development server, so this mount is skipped.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
