# Cloud-Based Student Assignment Submission & Feedback Portal

## Abstract

The project is a web portal that lets teachers publish assignments and return grades and feedback while students submit coursework and track its status. It uses React for the browser interface, Firebase Authentication for identity, Firestore for structured metadata, Firebase Storage for private file bytes, Firebase Functions for event processing, and FastAPI for a role-checked REST API. The API validates Firebase ID tokens before accessing Firebase through the Admin SDK.

## Introduction and problem statement

Assignment exchange through email and removable media makes it difficult to track deadlines, latest versions, private files, and feedback. The project provides a central browser-based workflow for students and teachers with one source of truth for assignment state and grading.

## Objectives

- Build student and teacher workflows with role-based access.
- Store assignment metadata and files in appropriate managed cloud services.
- Validate files and enforce deadline, resubmission, grading, and ownership rules on the server.
- Provide an executable React/Firebase/FastAPI architecture and local emulator path.
- Document security, deployment, test strategy, and scaling considerations.

## Existing system and proposed system

The manual existing approach uses email, shared folders, and separate mark sheets. It can create multiple competing versions and makes ownership checks difficult. The proposed portal centralizes coursework and submissions. Firestore stores document metadata and relationships; private Storage stores bytes; FastAPI verifies identity and authorization before mutations or downloads.

## User roles

Students register using Firebase Authentication and can view work, upload/resubmit according to policy, download their own files, and view their own marks and feedback. Teachers are promoted through an administrator-controlled script and can manage their courses and grade submissions in those courses. There is no end-user admin dashboard in this MVP.

## Cloud computing concepts

The hosted portal is a SaaS-style web app. Firebase Hosting provides managed static hosting (PaaS); Cloud Run operates the FastAPI container; Firebase Authentication, Firestore, and Cloud Storage are managed cloud services. IaaS concepts appear through Google Cloud IAM, network boundaries, service identities, and resource permissions. Firebase Functions demonstrate event-driven/serverless processing. Autoscaling, availability, logging, monitoring, backup, and billing alerts are supplied or configured through the cloud provider and deployment operations.

## Technology stack

React 19 and Vite form the frontend. Firebase Authentication handles email/password identity. FastAPI and Firebase Admin SDK provide protected REST endpoints. Cloud Firestore stores profiles, courses, assignments, submissions, and analytics. Cloud Storage stores private uploaded files. Cloud Functions process submission-created events and recalculate analytics. Firebase Hosting serves the frontend and proxies `/api/**` to a Cloud Run service.

## Architecture

Browser → Firebase Authentication → React UI → FastAPI with Firebase ID token → Firebase Admin authorization → Firestore and private Cloud Storage. A Firestore trigger computes deadline status and updates counters; a scheduled function rebuilds analytics. Firestore and Storage rules deny browser client data access; all application data access passes through FastAPI. Admin SDK bypasses rules, so backend authorization is mandatory.

## Database design

Firestore collections include `users/{uid}`, `courses/{courseId}`, `assignments/{assignmentId}`, `submissions/{submissionId}`, `submissionCounters/{counterId}`, `analytics/{courseId_assignmentId}`, and `processedEvents/{eventId}`. IDs reference related documents. A Firestore transaction increments a deterministic per-student/per-assignment version counter while recording a submission. Firestore indexes support assignment/student queries. File bytes are excluded from Firestore documents to keep database reads, writes, and backups focused on metadata.

## Cloud storage design

Files use an opaque path such as `assignments/{assignmentId}/{studentUid}/{submissionId}/{safeFileName}`. The API accepts multipart upload, validates extension and size, stores the object, then creates metadata. If metadata storage fails, it tries to delete the new object. Downloads are streamed only after ownership checks. No public download URL is persisted. Production must keep the bucket private and use least-privilege service identity.

## Authentication and authorization

The frontend uses Firebase Auth email/password. It sends a Firebase ID token in the Authorization header. FastAPI verifies the token and fetches the server-controlled Firestore role profile. New user profiles default to student; only an administrator with Firebase Admin credentials can promote a teacher. API routes check role and course/submission ownership. Firestore and Storage client rules deny all direct access; Admin SDK is used only on trusted backend/function runtime.

## Assignment management

Teachers create courses and assignments with title, description, deadline with timezone, maximum marks, allowed extensions, maximum file size, and resubmission policy. Teacher ownership is checked on create/update/delete. Assignments with submissions cannot be deleted. Students can list and view assignment details.

## Submission and deadline workflow

The student selects a file; the browser performs friendly checks, while the backend independently validates extension, size, assignment existence, deadline policy, and resubmission policy. Server UTC time is compared with the UTC assignment deadline. A transactional counter assigns the next version. File metadata includes student, course, assignment, object path, timestamp, version, and late status. The Cloud Function independently processes the new record and updates per-assignment analytics. Client clocks are not trusted.

## Feedback and grading

Teachers can download submissions for courses they own. Grade submission validates that marks are not negative or above maximum and limits feedback length. The API writes marks, feedback, grading timestamp, and `GRADED` status. Students can read/download only their own submission and see returned feedback.

## REST API

All application endpoints require Firebase ID tokens except health. Implemented endpoints include profile read/update; course list/create; assignment list/create/get/update/delete; student submit and list-own-submissions; teacher list submissions and list assignment submissions; get submission and feedback; grade; and private file download. FastAPI exposes OpenAPI docs at `/docs`. Status codes distinguish authentication failure (401), forbidden role (403), missing/hidden resources (404), policy conflicts (409), oversized files (413), invalid file extensions (415), and input validation (422).

## Implementation and folder structure

`frontend/src/pages/App.jsx` provides sign-in/registration and role dashboards. `frontend/src/services/` configures Firebase Auth and the token-bearing API client. `backend/app/main.py` creates FastAPI; `routes/` implements endpoints; `services/` initializes Firebase Admin and verifies identity; `models/` holds request schemas. `cloud/` stores Firestore/Storage rules, indexes, and Functions. Firebase Hosting and emulator wiring are in `firebase.json`.

## Testing

The backend test suite covers health, rejection of missing Firebase tokens, and student denial when creating a course. GitHub Actions runs backend pytest and frontend production build. Emulator integration and manual cases should cover valid/invalid/oversized uploads, late status, versioning, other-student access denial, teacher course ownership, grading limits, Cloud Function analytics, and download privacy. Record actual results and date in the final course submission after running the tests.

## Cloud deployment

Firebase Hosting serves the Vite build. The `/api/**` rewrite targets Cloud Run service `assignment-api` in `asia-south1`. Cloud Run receives project/bucket/CORS configuration and uses its runtime service identity. Deploy Firestore indexes/rules, Storage rules, Functions, and Hosting with Firebase CLI. Local development can use Firebase Emulator Suite. Current Firebase Storage provisioning and Cloud Functions deployment require a linked Blaze billing account; check current quotas and pricing and configure budget alerts before enabling cloud resources.

## Security

Implemented controls include Firebase password auth, ID-token verification, server-side role and resource ownership checks, protected Firestore profiles, deny-by-default client rules, opaque object paths, size/extension checks, marks validation, and private API downloads. Production additions include malware scanning, signature/MIME inspection, audit logs, least-privilege IAM review, secret management, backups, retention controls, rate limiting, monitoring alerts, and recovery testing. Do not commit service account keys or use real student data in a demo.

## Scalability and failure handling

For a small class, one Cloud Run service, Firestore, and Storage are adequate. At larger scale, use Cloud Run concurrency/autoscaling, Firestore indexes and pagination, Cloud Storage, and queue-backed scanning/notifications. High-volume deadline peaks may use signed, scoped multipart uploads with idempotency and reconciliation. Upload metadata failure triggers object cleanup; a trigger event ID prevents duplicate analytics counting; the daily job rebuilds aggregates. Add bounded retry for transient failures and never retry authorization or validation errors blindly.

## Results, advantages, and limitations

The implementation follows the selected React/Firebase architecture and provides role-specific workflows, private storage, validated REST operations, server-side deadline and grading logic, and Firebase serverless analytics. It centralizes records and supports remote use. It is an educational MVP: it does not include enrollment management, admin UI, password recovery screen, antivirus service, assignment rubric, complete audit console, or production monitoring dashboards. Firebase Storage, Cloud Functions, and Cloud Run may require billing setup even where a service has some no-cost usage.

## Future scope and conclusion

Next additions include enrollment management, notifications, rubric grading, malware scanning, access audit logs, pagination, signed direct uploads, better backup/restore automation, analytics visualization, accessibility review, and production load/security testing. This project demonstrates a managed-cloud application architecture that keeps user identity, relational-style metadata, and large file objects in suitable services while enforcing access through a trusted API.


