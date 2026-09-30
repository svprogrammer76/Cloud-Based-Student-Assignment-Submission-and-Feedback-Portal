const { onDocumentCreated } = require("firebase-functions/v2/firestore");
const { onSchedule } = require("firebase-functions/v2/scheduler");
const { logger } = require("firebase-functions");
const { initializeApp } = require("firebase-admin/app");
const { getFirestore, FieldValue } = require("firebase-admin/firestore");

initializeApp();
const db = getFirestore();

// Server-side deadline classification and idempotent per-assignment counters.
exports.processSubmission = onDocumentCreated("submissions/{submissionId}", async event => {
  const snapshot = event.data;
  if (!snapshot) return;
  const row = snapshot.data();
  const assignmentRef = db.collection("assignments").doc(row.assignmentId);
  const metricsRef = db.collection("analytics").doc(`${row.courseId}_${row.assignmentId}`);
  const eventRef = db.collection("processedEvents").doc(event.id);
  await db.runTransaction(async tx => {
    const [processed, assignmentSnap, metricsSnap, currentSubmission] = await Promise.all([
      tx.get(eventRef), tx.get(assignmentRef), tx.get(metricsRef), tx.get(snapshot.ref),
    ]);
    if (processed.exists) return;
    const assignment = assignmentSnap.data() || {};
    const currentRow = currentSubmission.data() || row;
    const dueAt = assignment.dueAt ? new Date(assignment.dueAt) : null;
    const submittedAt = new Date(currentRow.submittedAt);
    const late = Boolean(dueAt && submittedAt > dueAt);
    const prior = metricsSnap.data() || { total: 0, late: 0 };
    const total = prior.total + 1;
    const lateCount = prior.late + (late ? 1 : 0);
    tx.update(snapshot.ref, { late, status: currentRow.marks == null ? (late ? "LATE" : "SUBMITTED") : "GRADED" });
    tx.set(metricsRef, { courseId: row.courseId, assignmentId: row.assignmentId, total, late: lateCount,
      onTimePct: total ? ((total - lateCount) / total) * 100 : 0, updatedAt: FieldValue.serverTimestamp() });
    tx.set(eventRef, { submissionId: snapshot.id, processedAt: FieldValue.serverTimestamp() });
  });
  logger.info("Submission processed", { submissionId: snapshot.id });
});

// Daily repair/rebuild job makes analytics recoverable if a trigger failed during an outage.
exports.rebuildDailyAnalytics = onSchedule("every 24 hours", async () => {
  const totals = new Map();
  for await (const doc of db.collection("submissions").stream()) {
    const row = doc.data();
    const key = `${row.courseId}_${row.assignmentId}`;
    const stat = totals.get(key) || { courseId: row.courseId, assignmentId: row.assignmentId, total: 0, late: 0 };
    stat.total += 1;
    if (row.late) stat.late += 1;
    totals.set(key, stat);
  }
  let batch = db.batch();
  let writes = 0;
  for (const [key, stat] of totals) {
    batch.set(db.collection("analytics").doc(key), { ...stat, onTimePct: ((stat.total - stat.late) / stat.total) * 100, updatedAt: FieldValue.serverTimestamp() });
    if (++writes === 400) { await batch.commit(); batch = db.batch(); writes = 0; }
  }
  if (writes) await batch.commit();
});
