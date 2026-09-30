# Cloud-Based Student Assignment Submission & Feedback Portal

An Option B implementation using React + Vite, Firebase Authentication, Cloud Firestore, private object storage, and a Python FastAPI REST API. The browser signs users in with Firebase Authentication; FastAPI verifies every Firebase ID token and applies role and ownership checks. The no-billing cloud profile uses Render Free for the combined app/API and Supabase Storage for private files. Local emulator development stores uploads under `backend/local_uploads/`.

> **No-billing deployment profile:** Render Free hosts the React/FastAPI app, Firebase Spark provides Authentication and Firestore within its quotas, and a private Supabase Storage bucket stores uploaded files. This avoids linking a payment method. Supabase free projects can pause after inactivity and Render free web services sleep while idle. Optional Firebase Cloud Storage/Cloud Run deployment requires a billing-linked Google project; check [Firebase pricing](https://firebase.google.com/pricing) and [Cloud Storage billing requirements](https://firebase.google.com/docs/storage/faqs-storage-changes-announced-sept-2024) before choosing that profile.

## What the project does

Teachers create courses and assignments, set UTC deadlines and file policies, review course submissions, download files, and return marks and feedback. Students register/sign in, view assignments, upload or resubmit permitted files, check submission status, download their own work, and read feedback. The Firebase Function for submission analytics is included for the optional billing-linked Firebase deployment profile.

## Project structure

```text
.
├── .firebaserc.example
├── .github/workflows/tests.yml
├── firebase.json
├── render.yaml                       # No-billing Render deployment blueprint
├── frontend/
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   └── src/
│       ├── components/.gitkeep       # Reserved; reusable UI is currently in pages/App.jsx
│       ├── pages/App.jsx              # Auth flow and role dashboards
│       ├── services/api.js            # Bearer-token API client
│       ├── services/firebase.js       # Firebase Auth client/config
│       ├── utils/.gitkeep              # Reserved for shared frontend helpers
│       ├── main.jsx
│       └── style.css
├── backend/
│   ├── .env.example
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                    # FastAPI app and route registration
│   │   ├── config.py
│   │   ├── middleware/request_id.py
│   │   ├── models/schemas.py
│   │   ├── routes/                    # Profile, courses, assignments, submissions
│   │   ├── scripts/promote_teacher.py
│   │   ├── services/                  # Firebase Admin, local/cloud storage, token verification, RBAC
│   │   └── utils/                     # Reserved shared backend helpers
│   └── tests/test_api.py
├── cloud/
│   ├── firestore/
│   │   ├── firestore.rules            # Denies direct client data access
│   │   └── firestore.indexes.json
│   ├── functions/
│   │   ├── index.js                   # Submission trigger and analytics job
│   │   ├── package.json
│   │   └── package-lock.json
│   └── storage/storage.rules          # Denies direct client file access
├── docs/PROJECT_REPORT.md
├── legacy-flask/                      # Archived Flask/SQLite prototype
├── reports/.gitkeep                   # Put final report exports here
├── sample_files/.gitkeep              # Add dummy assignment files here
└── screenshots/.gitkeep               # Add demo screenshots here
```

`.env`, `.env.local`, service-account JSON keys, virtual environments, `node_modules/`, build output, test caches, and local `instance/` data are ignored local files. They may appear in VS Code after setup but are intentionally absent from this repository tree. Never commit service-account keys.

## Architecture

```mermaid
flowchart LR
  U[Student or teacher browser] --> H[Firebase Authentication]
  U --> R[React + Vite interface]
  R -->|Firebase ID token| API[FastAPI REST API]
  API -->|verify ID token and check role/ownership| AUTH[Firebase Admin SDK]
  API --> DB[(Cloud Firestore)]
  API --> OBJ[(Private Supabase Storage bucket)]
  DB -. optional billing-linked profile .-> FN[Cloud Function: analytics]
  FN -.-> DB
  R --> HOST[Render Free: React + FastAPI]
  HOST --> API
```

Firestore stores user profiles, courses, assignments, submissions, and analytics metadata. The private Supabase Storage bucket contains deployed uploaded bytes; local emulators use the local upload folder. The object's key is recorded in Firestore; users never receive a permanent public file URL. FastAPI checks the student's ownership or teacher's course ownership before downloading. The trusted backend uses a Firebase Admin service identity and a server-only Supabase service-role key, so backend validation is mandatory.

## Technology choices

- **Frontend:** React 19, Vite, Firebase Web SDK.
- **Authentication:** Firebase Authentication email/password. Registration is student-only. Promote teacher accounts with the admin script.
- **Database:** Cloud Firestore.
- **File storage:** Supabase Storage private bucket for no-billing deployment; local folder for emulator runs.
- **REST API:** Python FastAPI, Firebase Admin SDK, Firebase ID-token verification.
- **Serverless:** Firebase Functions source processes submission events and rebuilds analytics; deploying those functions requires a billing-linked Firebase project and is outside the no-billing profile.
- **Hosting:** Render Free serves the built React app and FastAPI API from one service. Free web services sleep while idle; files remain in Supabase Storage.

## Data model

- `users/{uid}`: `name`, `email`, `role`, timestamps.
- `courses/{courseId}`: `name`, `description`, `teacherId`, `createdAt`.
- `assignments/{assignmentId}`: `courseId`, `title`, `description`, UTC `dueAt`, `maxMarks`, `allowedTypes`, `maxFileSizeMB`, `allowResubmission`, `createdBy`, `createdAt`.
- `submissions/{submissionId}`: `assignmentId`, `courseId`, `studentUid`, `studentName`, `fileName`, private `storagePath`, `size`, `mime`, UTC `submittedAt`, `version`, `late`, `status`, optional marks/feedback/grading timestamp.
- `submissionCounters/{counterId}`: transactionally incremented version counter for one student and assignment.
- `analytics/{courseId_assignmentId}`: total submissions, late count, on-time percentage, update time.
- `processedEvents/{eventId}`: trigger idempotency record.

Primary relationships are represented by IDs. Firestore is document-oriented rather than relational; API queries and indexes support access patterns. Large file contents stay in object storage because that service is optimized for durable blobs and transfer.

## Setup on Windows

### 1. Install prerequisites

Install Node.js 22 (20 is also currently supported by Firebase Functions), Python 3.11+, Git, and Java JDK 21 or newer. Firestore Emulator needs Java; current emulator releases require Java 21+. Install Firebase CLI:

```powershell
npm.cmd install -g firebase-tools
firebase.cmd --version
```

The earlier `.venv` in this workspace belonged to the Flask version; create a fresh environment for the FastAPI backend.

### 2. Prepare no-billing local emulators

The first run below uses Firebase Auth, Firestore, and Functions emulators with a local folder for uploaded files. It does not need a Firebase Console project, service-account key, or billing account. For no-billing cloud deployment, use the Render + Firebase Spark + private Supabase Storage profile below. Firebase Cloud Storage, Cloud Functions, and Cloud Run deployment are optional and require a billing-linked Google project.

### 3. Install packages

From the project root in PowerShell:

```powershell
cd frontend
npm.cmd install
Copy-Item .env.example .env.local
cd ..\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
cd ..\cloud\functions
npm.cmd ci
cd ..\..
```

Edit `frontend/.env.local` and set these local demo values:

```dotenv
VITE_FIREBASE_API_KEY=demo-api-key
VITE_FIREBASE_AUTH_DOMAIN=demo-assignment-portal.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=demo-assignment-portal
VITE_FIREBASE_STORAGE_BUCKET=demo-assignment-portal.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=123456789000
VITE_FIREBASE_APP_ID=1:123456789000:web:localdemo
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_USE_FIREBASE_EMULATORS=true
```

Edit `backend/.env` with these values:

```dotenv
FIREBASE_PROJECT_ID=demo-assignment-portal
FIREBASE_STORAGE_BUCKET=demo-assignment-portal.appspot.com
GOOGLE_APPLICATION_CREDENTIALS=
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174
MAX_UPLOAD_BYTES=16777216
ALLOW_LATE_SUBMISSIONS=true
ALLOW_RESUBMISSIONS=true
LOCAL_STORAGE_DIR=local_uploads
FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
```

The `demo-` project ID tells Firebase CLI to use an emulator-only project. Keep the exact same ID in both files. `local_uploads` is created below `backend/` when the first file is submitted. To activate the Python environment in a new terminal, use `cd backend` followed by `.\.venv\Scripts\Activate.ps1`.

### 4. Start the emulators and app

Terminal 1, from the project root. First startup downloads emulator binaries:

```powershell
firebase.cmd emulators:start --project demo-assignment-portal --only auth,firestore,functions,pubsub
```

You should see Auth on port `9099`, Firestore on `8080`, Functions on `5001`, and the Emulator UI on `4000`. Terminal 2, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Terminal 3, from `frontend/`:

```powershell
npm.cmd run dev
```

Open `http://localhost:5173`. Register an account to use as the demo teacher. Sign out, then in Terminal 4 run from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m app.scripts.promote_teacher teacher@example.edu
```

Sign out and back in so the API reads the updated role. The script talks to the Auth and Firestore emulators because the emulator variables are in `backend/.env`. The emulator UI at `http://127.0.0.1:4000` lets you inspect test users and Firestore documents. Uploaded files are stored in `backend/local_uploads/`.

As the teacher, create a course and assignment. Then open a second browser/private window, register a student, and submit a PDF. Return to the teacher window to download and grade the work. Student feedback appears on the student dashboard. The API docs are at `http://127.0.0.1:8000/docs` and its health check is `http://127.0.0.1:8000/health`.

### 5. Optional Firebase Cloud Storage setup (billing linked)

The no-billing cloud deployment below does not use Firebase Storage. If you intentionally use Firebase Cloud Storage instead, create a Firebase project, enable Email/Password Authentication, Firestore, and Storage, then configure a web app and backend identity. Cloud Storage requires a linked Blaze billing account as of February 3, 2026; no-cost quotas may apply, but usage over quotas can be billed. Do not use this optional profile if you do not want to link billing.

### 6. Demonstrate the workflow

Sign in as teacher, create a course, then publish an assignment with a future deadline. Sign in as a student in a second browser/private window, register, and upload a PDF. Return to the teacher account, download and grade the file, then sign back into the student account and verify the grade and feedback. The student can download only their own file. Test late status by creating an assignment with a past UTC deadline while late submissions are enabled.

## REST API

All `/api` routes except `/health` require `Authorization: Bearer <Firebase ID token>`.

| Method | Endpoint | Access |
|---|---|---|
| `GET`, `PUT` | `/api/profile` | Signed-in user; profile update cannot change role |
| `GET`, `POST` | `/api/courses` | Signed in; teacher creates a course |
| `GET`, `POST` | `/api/assignments` | Signed in; teacher creates within own course |
| `GET`, `PUT`, `DELETE` | `/api/assignments/{id}` | Owner teacher; delete is blocked if submissions exist |
| `POST` | `/api/assignments/{id}/submit` | Student multipart upload |
| `GET` | `/api/submissions/me` | Student's own submissions |
| `GET` | `/api/teacher/submissions` | Teacher's courses |
| `GET` | `/api/assignments/{id}/submissions` | Owning teacher |
| `GET` | `/api/submissions/{id}` | Owning student or course teacher |
| `GET` | `/api/submissions/{id}/feedback` | Owning student |
| `POST` | `/api/submissions/{id}/grade` | Course teacher; marks limited to maximum |
| `GET` | `/api/submissions/{id}/download` | Owning student or course teacher |

Expected errors include 401 missing/expired token, 403 role denial, 404 unavailable resource, 409 disallowed operation/deadline, 413 too large, and 415 invalid extension. FastAPI request schema errors return 422.

## Security and reliability

Firebase Auth handles passwords; the backend verifies ID tokens and obtains roles from protected Firestore profile documents. Server-side checks enforce course ownership and private file access. Upload validation checks configured extension and size limits and uses random object identifiers; production should add MIME signature checks and malware scanning. Never treat a browser-supplied UID, role, timestamp, deadline status, or filename as authorization truth. Use HTTPS, private bucket policies, secret management, retention policies, and operational audit logs before production. Firebase Admin credentials and the Supabase service-role key belong only in Render environment variables, never source control.

The upload sequence stores the object, then creates metadata inside a Firestore transaction that increments the version counter; if metadata creation fails, the object is deleted. Retriable clients should avoid blind duplicate submits; production can add explicit idempotency keys. The Cloud Function uses the event ID to avoid double-counting when a trigger retries, and the scheduled job rebuilds analytics.

## Cloud deployment without a billing account

This free profile deploys one combined React/FastAPI service on Render Free, keeps Firebase Authentication and Firestore on the Spark plan, and stores files in a private Supabase Storage bucket. Firebase Functions source remains in `cloud/functions/`, but Firebase Functions are not deployed in this profile.

1. Create a Firebase project on the no-cost Spark plan. Enable Email/Password Authentication and create a Firestore database. Register a Web app and copy its Firebase config values. Create a Firebase Admin service-account JSON key for the backend; keep it out of Git.
2. Create a Supabase Free project and a **private** Storage bucket named `assignment-submissions`. Copy the project URL and service-role key. The key is secret and must only go into Render's backend environment.
3. Push the project to a GitHub repository. In Render, choose **New → Blueprint**, connect that repository, and let Render read the root `render.yaml` file.
4. Enter the Firebase web config values (`VITE_FIREBASE_*`) requested by the blueprint. Enter `FIREBASE_PROJECT_ID`, the complete `FIREBASE_SERVICE_ACCOUNT_JSON`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` as backend deployment variables. Do not put service-account JSON or the Supabase service-role key in source files.
5. After deployment, add the Render `onrender.com` hostname to Firebase Authentication's authorized domains. Open the Render URL and `/health`; create new demo accounts because emulator users are local and do not transfer.
6. Promote the cloud demo teacher in Firebase Console: copy the teacher's UID from Authentication, open Firestore `users/{uid}`, and change only `role` from `student` to `teacher`. Sign out and back in.

The free profile avoids a payment method. Render Free services sleep after 15 minutes without requests, and the first request after sleep may take about a minute. Render's free filesystem is temporary, so files use Supabase Storage instead. Supabase Free includes 1 GB file storage and may pause projects after seven days of low activity. Review [Render Free limits](https://render.com/docs/free), [Supabase pricing](https://supabase.com/pricing), and [Supabase project pausing](https://supabase.com/docs/guides/platform/free-project-pausing). This is a student demo profile, not a production availability guarantee.

The alternative Firebase Hosting + Cloud Run + Firebase Cloud Storage deployment is intentionally not used here because those services require linking a billing account. Do not select a paid plan for this no-billing setup.

## Testing and proof checklist

Run backend tests from `backend/` with `pytest -q`; build frontend with `npm run build` from `frontend/`. GitHub Actions performs both checks. Manual proof: registration/login, teacher promotion, role rejection, course/assignment creation, valid/invalid/oversized upload, on-time/late status, versioned resubmission, cross-student download denial, teacher grading, student feedback, function analytics, Firebase rules, API docs, emulator suite, and hosted deployment. Save dummy-data screenshots in `screenshots/` with filenames such as `01-login.png`, `02-teacher-dashboard.png`, `03-student-upload.png`, `04-private-storage.png`, `05-grade-feedback.png`, `06-api-docs.png`, and `07-tests.png`.

## Local folder map for the original setup guide

| Guide file/snippet | Destination in this repository |
|---|---|
| React/Firebase initialization | `frontend/src/services/firebase.js` (already implemented; fill `frontend/.env.local`) |
| Upload + Firestore metadata | Replaced by React form in `frontend/src/pages/App.jsx` calling protected FastAPI upload route in `backend/app/routes/submissions.py` |
| Firestore rules | `cloud/firestore/firestore.rules` (intentionally stricter because API uses Admin SDK) |
| Storage rules | `cloud/storage/storage.rules` |
| Cloud Function | `cloud/functions/index.js` |
| Similarity/auto-grade AI | Optional future service; not part of Option B MVP |
| Firebase Hosting config | Root `firebase.json` |
| Backend tests | `backend/tests/`; frontend build checked by GitHub Actions |
| Feedback form | Teacher grading UI in `frontend/src/pages/App.jsx`, persisted by the grade API route |

The guide’s AI model and Cloud Run ML API are optional Step 4 extensions. They are intentionally not mixed into the assignment API.

## Limitations and next steps

This is an educational project, not a production LMS. It has no course enrollment workflow, password reset screen, antivirus scanner, audit log viewer, rubric editor, notifications, pagination, or production monitoring dashboards. For real deployments, add those controls, test rules and IAM in a staging project, run load and security reviews, and establish backup/restore procedures.

## Resume proof

- Built a React and FastAPI assignment portal using Firebase Authentication, Firestore, private object storage, and Firebase Functions source.
- Implemented Firebase ID-token verification, role/course authorization, versioned deadline-aware uploads, and private per-student downloads.
- Added automated API authorization tests, Cloud Function analytics, Firebase security rules, emulator configuration, and CI build checks.

## Interview practice

1. **Explain your project.** Teachers publish coursework in the portal; students submit files and later see grades and feedback. Firebase handles identity, Firestore stores records, private Supabase Storage holds deployed files, and FastAPI checks the user's Firebase token and resource permissions.
2. **Why use object storage for submissions?** It is designed for large durable objects, while Firestore documents stay small and searchable. Firestore stores the private object path and submission metadata.
3. **How is a student's file kept private?** The Supabase bucket is private and only the FastAPI backend holds its service-role key. The API verifies the ID token and checks submission ownership before streaming the file.
4. **How does role authorization work?** Registration only creates student profiles. A trusted admin promotes teachers. Every protected API route reads the role from Firestore and checks ownership server-side.
5. **How do you determine whether a submission is late?** The backend uses server UTC time and the saved UTC deadline. A Firebase Function independently processes the new submission and updates per-assignment analytics.
6. **How are resubmission versions assigned?** A Firestore transaction increments a per-student/per-assignment counter while it writes submission metadata, preventing concurrent retries from receiving the same version.
7. **What happens if the file saves but metadata fails?** The API attempts to delete the newly uploaded object. Operational reconciliation can find any orphan object if cleanup itself fails.
8. **How would you scale the system?** Host React on a CDN, scale stateless API instances, use Firestore and private object storage, and move scanning/notifications to queue-backed functions.
9. **Can this be tested without deploying?** Yes. Firebase Emulator Suite runs Auth, Firestore, Storage, and Functions locally; the React app can connect to Auth Emulator and the backend to the other emulators.
10. **What should be added before real student data is used?** Course enrollment, malware scanning, audit logs, stricter file inspection, backups, monitoring, IAM review, privacy/retention policy, and load/security testing.

## Author

Add your name, course, institution, and project date. Use dummy users and files for demos.
