import React, { useEffect, useState } from "react";
import { createUserWithEmailAndPassword, onAuthStateChanged, signInWithEmailAndPassword, signOut, updateProfile } from "firebase/auth";
import { auth, firebaseConfigured } from "../services/firebase";
import { api, json } from "../services/api";

function Field({ label, ...props }) { return <label className="field">{label}<input {...props} /></label>; }

export default function App() {
  const [identity, setIdentity] = useState(null);
  const [profile, setProfile] = useState(null);
  const [page, setPage] = useState("login");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [courses, setCourses] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [submissions, setSubmissions] = useState([]);

  async function loadProfile(user) {
    const token = await user.getIdToken();
    const value = await api("/api/profile", token);
    setIdentity(user); setProfile(value); setPage("dashboard");
  }
  useEffect(() => {
    if (!firebaseConfigured) return;
    return onAuthStateChanged(auth, user => {
      if (user) loadProfile(user).catch(e => setError(e.message));
      else { setIdentity(null); setProfile(null); setPage("login"); }
    });
  }, []);

  async function refresh() {
    if (!identity) return;
    const token = await identity.getIdToken();
    const [c, a, s] = await Promise.all([
      api("/api/courses", token), api("/api/assignments", token),
      api(profile.role === "teacher" ? "/api/teacher/submissions" : "/api/submissions/me", token),
    ]);
    setCourses(c); setAssignments(a); setSubmissions(s);
  }
  useEffect(() => { if (profile && identity) refresh().catch(e => setError(e.message)); }, [profile, identity]);

  async function run(action) {
    setError(""); setNotice(""); setBusy(true);
    try { await action(); } catch (e) { setError(e.message || "Something went wrong"); }
    finally { setBusy(false); }
  }
  async function authenticate(event) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    await run(async () => {
      if (page === "register") {
        const credential = await createUserWithEmailAndPassword(auth, form.get("email"), form.get("password"));
        await updateProfile(credential.user, { displayName: form.get("name") });
        const token = await credential.user.getIdToken();
        const saved = await api("/api/profile", token, json("PUT", { name: form.get("name") }));
        setIdentity(credential.user); setProfile(saved); setNotice("Account created. You are signed in as a student."); setPage("dashboard");
      } else {
        await signInWithEmailAndPassword(auth, form.get("email"), form.get("password"));
      }
    });
  }
  async function doSignOut() { await signOut(auth); setCourses([]); setAssignments([]); setSubmissions([]); }
  async function createCourse(event) {
    event.preventDefault(); const element = event.currentTarget; const form = new FormData(element); const token = await identity.getIdToken();
    await run(async () => { await api("/api/courses", token, json("POST", { name: form.get("name"), description: form.get("description") })); element.reset(); setNotice("Course created."); await refresh(); });
  }
  async function createAssignment(event) {
    event.preventDefault(); const element = event.currentTarget; const form = new FormData(element); const token = await identity.getIdToken();
    const item = { courseId: form.get("courseId"), title: form.get("title"), description: form.get("description"), dueAt: new Date(form.get("dueAt")).toISOString(), maxMarks: Number(form.get("maxMarks")), allowedTypes: form.get("allowedTypes").split(",").map(x => x.trim().replace(/^\./, "").toLowerCase()).filter(Boolean), maxFileSizeMB: Number(form.get("maxFileSizeMB")), allowResubmission: form.get("allowResubmission") === "on" };
    await run(async () => { await api("/api/assignments", token, json("POST", item)); element.reset(); setNotice("Assignment created."); await refresh(); });
  }
  async function upload(event, assignment) {
    event.preventDefault(); const file = new FormData(event.currentTarget).get("file");
    if (!file?.size) return setError("Choose a file first.");
    const ext = file.name.split(".").pop().toLowerCase();
    if (!assignment.allowedTypes.includes(ext)) return setError(`Allowed types: ${assignment.allowedTypes.join(", ")}`);
    if (file.size > assignment.maxFileSizeMB * 1024 * 1024) return setError(`File exceeds ${assignment.maxFileSizeMB} MB.`);
    const token = await identity.getIdToken(); const body = new FormData(); body.append("file", file);
    await run(async () => { await api(`/api/assignments/${assignment.id}/submit`, token, { method: "POST", body }); setNotice("Submission uploaded."); await refresh(); });
  }
  async function grade(event, submission) {
    event.preventDefault(); const form = new FormData(event.currentTarget); const token = await identity.getIdToken();
    await run(async () => { await api(`/api/submissions/${submission.id}/grade`, token, json("POST", { marks: Number(form.get("marks")), feedback: form.get("feedback") })); setNotice("Grade and feedback saved."); await refresh(); });
  }
  async function download(submission) {
    const token = await identity.getIdToken();
    await run(async () => { const blob = await api(`/api/submissions/${submission.id}/download`, token); const href = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = href; link.download = submission.fileName; link.click(); URL.revokeObjectURL(href); });
  }

  if (!firebaseConfigured) return <main className="setup"><div className="brand-mark">CP</div><h1>Connect Firebase to start</h1><p>Copy <code>frontend/.env.example</code> to <code>frontend/.env.local</code>, then enter the web app settings from Firebase Console.</p><p>See the root README for the exact Firebase setup steps.</p></main>;
  if (!identity || !profile) return <main className="auth-shell"><section className="auth-card"><div className="eyebrow">CLOUD CLASSROOM</div><h1>{page === "register" ? "Create your student account" : "Welcome back"}</h1><p className="subheading">Assignments, submissions, and feedback in one place.</p>{error && <div className="alert error">{error}</div>}<form onSubmit={authenticate} className="stack">{page === "register" && <Field label="Full name" name="name" required maxLength="120" autoComplete="name"/>}<Field label="Email address" name="email" type="email" required autoComplete="email"/><Field label="Password" name="password" type="password" required minLength="8" autoComplete={page === "register" ? "new-password" : "current-password"}/><button disabled={busy}>{busy ? "Please wait…" : page === "register" ? "Create account" : "Sign in"}</button></form><p className="switch">{page === "register" ? "Already registered?" : "New student?"} <button className="text-button" onClick={() => { setError(""); setPage(page === "register" ? "login" : "register"); }}>{page === "register" ? "Sign in" : "Create an account"}</button></p><p className="hint">Teacher accounts are created in Firebase Authentication and promoted by the project administrator.</p></section></main>;

  const submittedIds = new Set(submissions.map(s => s.assignmentId));
  return <div className="app-shell"><header className="topbar"><a className="logo" href="#home"><span className="logo-icon">C</span> Class<span>Cloud</span></a><nav><span className="role-pill">{profile.role}</span><span className="user-name">{profile.name}</span><button className="outline small" onClick={doSignOut}>Sign out</button></nav></header><main className="content"><div className="welcome"><div><div className="eyebrow">{profile.role === "teacher" ? "TEACHER WORKSPACE" : "STUDENT WORKSPACE"}</div><h1>{profile.role === "teacher" ? "Your classroom, at a glance." : `Good to see you, ${profile.name.split(" ")[0]}.`}</h1><p>{profile.role === "teacher" ? "Manage coursework, review submissions, and return feedback." : "Keep up with your assignments and feedback."}</p></div><button className="outline" onClick={() => refresh().catch(e => setError(e.message))}>Refresh data</button></div>{error && <div className="alert error">{error}</div>}{notice && <div className="alert success">{notice}</div>}
    <div className="stats"><div className="stat-card"><span>Assignments</span><b>{assignments.length}</b></div><div className="stat-card"><span>{profile.role === "teacher" ? "Submissions" : "To submit"}</span><b>{profile.role === "teacher" ? submissions.length : Math.max(0, assignments.length - submittedIds.size)}</b></div><div className="stat-card"><span>Late</span><b>{submissions.filter(s => s.status === "LATE").length}</b></div><div className="stat-card"><span>Graded</span><b>{submissions.filter(s => s.status === "GRADED").length}</b></div></div>
    {profile.role === "teacher" ? <><section className="panel"><div className="panel-heading"><div><div className="eyebrow">COURSE SETUP</div><h2>Create a course</h2></div></div><form className="form-grid" onSubmit={createCourse}><Field label="Course name" name="name" required placeholder="Cloud Computing"/><Field label="Description" name="description" placeholder="Optional course summary"/><button disabled={busy}>Add course</button></form></section><section className="panel"><div className="panel-heading"><div><div className="eyebrow">NEW COURSEWORK</div><h2>Publish an assignment</h2></div></div>{courses.length ? <form className="form-grid" onSubmit={createAssignment}><label className="field">Course<select name="courseId" required>{courses.map(c => <option value={c.id} key={c.id}>{c.name}</option>)}</select></label><Field label="Assignment title" name="title" required/><Field label="Deadline" name="dueAt" type="datetime-local" required/><Field label="Maximum marks" name="maxMarks" type="number" min="1" defaultValue="100" required/><Field label="Allowed file types" name="allowedTypes" defaultValue="pdf,docx,txt,zip"/><Field label="Maximum size (MB)" name="maxFileSizeMB" type="number" min="1" max="100" defaultValue="16"/><label className="field span-two">Instructions<textarea name="description" rows="2"/></label><label className="check"><input name="allowResubmission" type="checkbox" defaultChecked/> Allow resubmissions before grading</label><button disabled={busy}>Publish assignment</button></form> : <p className="empty">Create a course first, then publish its first assignment.</p>}</section><section><div className="section-heading"><div><div className="eyebrow">REVIEW QUEUE</div><h2>Recent submissions</h2></div></div>{submissions.length ? submissions.map(s => <SubmissionCard key={s.id} submission={s} assignments={assignments} courses={courses} download={download} grade={grade} busy={busy}/>) : <div className="empty panel">No submissions yet.</div>}</section></> : <section><div className="section-heading"><div><div className="eyebrow">YOUR COURSEWORK</div><h2>Assignments</h2></div></div>{assignments.length ? assignments.map(a => <AssignmentCard key={a.id} assignment={a} submission={submissions.find(s => s.assignmentId === a.id)} courseName={courses.find(c => c.id === a.courseId)?.name} upload={upload} download={download} busy={busy}/>) : <div className="empty panel">Your teachers haven’t published assignments yet.</div>}</section>}</main><footer>ClassCloud · Secure coursework and feedback</footer></div>;
}

function AssignmentCard({ assignment: a, submission, courseName, upload, download, busy }) {
  return <article className="assignment-card"><div className="assignment-top"><div className="assignment-icon">▤</div><div className="assignment-title"><span className="eyebrow">{courseName || "COURSEWORK"}</span><h3>{a.title}</h3></div><span className={`status ${submission?.status?.toLowerCase() || "pending"}`}>{submission?.status || "NOT SUBMITTED"}</span></div><p className="description">{a.description || "Review the instructions and submit your work before the deadline."}</p><div className="meta"><span>Due {new Date(a.dueAt).toLocaleString()}</span><span>{a.maxMarks} points</span></div>{submission && <div className="grade-box"><div><b>{submission.status === "GRADED" ? `${submission.marks} / ${a.maxMarks}` : `Version ${submission.version} · ${submission.status.toLowerCase()}`}</b>{submission.status === "GRADED" && <p>{submission.feedback || "No written feedback."}</p>}</div><button className="text-button" onClick={() => download(submission)}>Download submission</button></div>}{(!submission || (a.allowResubmission && submission.status !== "GRADED")) && <form className="upload-row" onSubmit={e => upload(e, a)}><input name="file" type="file" required/><button disabled={busy}>{submission ? "Resubmit work" : "Submit assignment"}</button></form>}</article>;
}

function SubmissionCard({ submission: s, assignments, courses, download, grade, busy }) {
  const assignment = assignments.find(a => a.id === s.assignmentId);
  return <article className="submission-card"><div className="submission-info"><div className="file-icon">FILE</div><div><h3>{s.studentName}</h3><p>{courses.find(c => c.id === s.courseId)?.name || "Course"} · {assignment?.title || "Assignment"} · {s.fileName}</p><span>Version {s.version} · {new Date(s.submittedAt).toLocaleString()} · {s.status}</span></div></div><button className="outline small" onClick={() => download(s)}>Download file</button><form className="grade-form" onSubmit={e => grade(e, s)}><Field label={`Marks (out of ${assignment?.maxMarks || "—"})`} name="marks" type="number" min="0" max={assignment?.maxMarks} defaultValue={s.marks ?? ""} required/><label className="field">Written feedback<textarea name="feedback" rows="2" maxLength="5000" defaultValue={s.feedback || ""}/></label><button disabled={busy}>Save feedback</button></form></article>;
}
