const test = require("node:test");
const assert = require("node:assert/strict");
const functionsTest = require("firebase-functions-test")({
  projectId: process.env.GCLOUD_PROJECT || "swift-shore-238707",
});
const { getFirestore } = require("firebase-admin/firestore");
const callables = require("../index");

const approveNotification = functionsTest.wrap(callables.approveNotification);
const archiveNotification = functionsTest.wrap(callables.archiveNotification);
const restoreArchivedNotification = functionsTest.wrap(callables.restoreArchivedNotification);
const onScraperUpdate = functionsTest.wrap(callables.onScraperUpdate);
const adminAuth = { uid: "admin-test", token: { admin: true } };

function uniqueId(label) {
  return `test_${label}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

test("approval requires an authenticated admin claim", async () => {
  await assert.rejects(
    approveNotification({ data: { notificationId: "unused" } }),
    (error) => error.code === "unauthenticated",
  );

  await assert.rejects(
    approveNotification({
      data: { notificationId: "unused" },
      auth: { uid: "not-admin", token: {} },
    }),
    (error) => error.code === "permission-denied",
  );
});

test("approval atomically publishes and creates one trigger without a URL", async () => {
  const db = getFirestore();
  const notificationId = uniqueId("approve");
  const draftRef = db.collection("notifications_draft").doc(notificationId);
  const publishedRef = db.collection("notifications").doc(notificationId);
  const triggerRef = db.collection("fcm_triggers").doc(`approval_${notificationId}_1`);
  const reviewRef = db.collection("notification_reviews").doc(`approved_${notificationId}_1`);

  await draftRef.set({
    id: notificationId,
    title: "  Test title  ",
    body: "Test body",
    category: "News",
    timestamp: new Date().toISOString(),
    status: "draft",
  });

  const firstResult = await approveNotification({
    data: { notificationId },
    auth: adminAuth,
  });
  assert.equal(firstResult.success, true);
  assert.equal(firstResult.alreadyPublished, false);

  const [draft, published, trigger, review] = await Promise.all([
    draftRef.get(),
    publishedRef.get(),
    triggerRef.get(),
    reviewRef.get(),
  ]);
  assert.equal(draft.exists, false);
  assert.equal(published.data().title, "Test title");
  assert.equal(published.data().approvedBy, adminAuth.uid);
  assert.equal(trigger.data().articleUrl, "");
  assert.deepEqual(trigger.data().topics, ["au_migration"]);
  assert.equal(trigger.data().sent, false);
  assert.equal(review.data().action, "approved");

  const retryResult = await approveNotification({
    data: { notificationId },
    auth: adminAuth,
  });
  assert.equal(retryResult.success, true);
  assert.equal(retryResult.alreadyPublished, true);

  const triggerQuery = await db.collection("fcm_triggers")
    .where("title", "==", "Test title")
    .get();
  assert.equal(triggerQuery.size, 1);

  await Promise.all([
    publishedRef.delete(),
    triggerRef.delete(),
    reviewRef.delete(),
  ]);
});

test("archive requires admin and atomically hides a published notification", async () => {
  const db = getFirestore();
  const notificationId = uniqueId("archive");
  const publishedRef = db.collection("notifications").doc(notificationId);
  const archivedRef = db.collection("notifications_archived").doc(notificationId);
  const reviewRef = db.collection("notification_reviews").doc(`archived_${notificationId}`);

  await assert.rejects(
    archiveNotification({ data: { notificationId } }),
    (error) => error.code === "unauthenticated",
  );

  await publishedRef.set({
    id: notificationId,
    title: "Published test",
    body: "Archive this notification",
    category: "News",
    status: "published",
  });

  const result = await archiveNotification({
    data: { notificationId, reason: "Incorrect information" },
    auth: adminAuth,
  });
  assert.equal(result.success, true);
  assert.equal(result.alreadyArchived, false);

  const [removed, archived, review] = await Promise.all([
    publishedRef.get(),
    archivedRef.get(),
    reviewRef.get(),
  ]);
  assert.equal(removed.exists, false);
  assert.equal(archived.data().status, "archived");
  assert.equal(archived.data().archivedBy, adminAuth.uid);
  assert.equal(archived.data().archiveReason, "Incorrect information");
  assert.equal(review.data().action, "archived");
  assert.equal(review.data().archiver, adminAuth.uid);

  const retry = await archiveNotification({
    data: { notificationId },
    auth: adminAuth,
  });
  assert.equal(retry.alreadyArchived, true);

  await Promise.all([archivedRef.delete(), reviewRef.delete()]);
});

test("restore requires admin and atomically returns an archive to drafts", async () => {
  const db = getFirestore();
  const notificationId = uniqueId("restore");
  const archivedRef = db.collection("notifications_archived").doc(notificationId);
  const draftRef = db.collection("notifications_draft").doc(notificationId);

  await assert.rejects(
    restoreArchivedNotification({ data: { notificationId } }),
    (error) => error.code === "unauthenticated",
  );

  await archivedRef.set({
    id: notificationId,
    title: "Archived test",
    body: "Restore this notification",
    category: "News",
    status: "archived",
    approvalGeneration: 1,
    approvedAt: "2026-01-01T00:00:00.000Z",
    approvedBy: "previous-admin",
    archivedAt: "2026-01-02T00:00:00.000Z",
    archivedBy: "previous-admin",
    archiveReason: "Needs correction",
    read: false,
  });

  const result = await restoreArchivedNotification({
    data: { notificationId },
    auth: adminAuth,
  });
  assert.equal(result.success, true);
  assert.equal(result.alreadyRestored, false);

  const [removed, draft, reviews] = await Promise.all([
    archivedRef.get(),
    draftRef.get(),
    db.collection("notification_reviews")
      .where("notificationId", "==", notificationId)
      .where("action", "==", "restored")
      .get(),
  ]);
  assert.equal(removed.exists, false);
  assert.equal(draft.data().status, "draft");
  assert.equal(draft.data().approvalGeneration, 2);
  assert.equal(draft.data().restoredBy, adminAuth.uid);
  assert.equal(draft.data().approvedAt, undefined);
  assert.equal(draft.data().archivedAt, undefined);
  assert.equal(draft.data().read, undefined);
  assert.equal(reviews.size, 1);
  assert.equal(reviews.docs[0].data().restorer, adminAuth.uid);

  const retry = await restoreArchivedNotification({
    data: { notificationId },
    auth: adminAuth,
  });
  assert.equal(retry.alreadyRestored, true);

  await Promise.all([
    draftRef.delete(),
    ...reviews.docs.map((review) => review.ref.delete()),
  ]);
});

test("reapproval after restore creates a new FCM trigger generation", async () => {
  const db = getFirestore();
  const notificationId = uniqueId("reapprove");
  const archivedRef = db.collection("notifications_archived").doc(notificationId);
  const publishedRef = db.collection("notifications").doc(notificationId);
  const oldTriggerRef = db.collection("fcm_triggers").doc(`approval_${notificationId}_1`);
  const newTriggerRef = db.collection("fcm_triggers").doc(`approval_${notificationId}_2`);
  const newReviewRef = db.collection("notification_reviews").doc(`approved_${notificationId}_2`);

  await archivedRef.set({
    id: notificationId,
    title: "Republish test",
    body: "This should create a fresh trigger",
    category: "News",
    status: "archived",
    approvalGeneration: 1,
  });
  await oldTriggerRef.set({ sent: true, title: "Previous publication" });

  await restoreArchivedNotification({ data: { notificationId }, auth: adminAuth });
  await approveNotification({ data: { notificationId }, auth: adminAuth });

  const [published, oldTrigger, newTrigger, newReview] = await Promise.all([
    publishedRef.get(),
    oldTriggerRef.get(),
    newTriggerRef.get(),
    newReviewRef.get(),
  ]);
  assert.equal(published.data().approvalGeneration, 2);
  assert.equal(oldTrigger.data().sent, true);
  assert.equal(newTrigger.exists, true);
  assert.equal(newTrigger.data().sent, false);
  assert.equal(newReview.data().action, "approved");

  const restoredReviews = await db.collection("notification_reviews")
    .where("notificationId", "==", notificationId)
    .where("action", "==", "restored")
    .get();
  await Promise.all([
    publishedRef.delete(),
    oldTriggerRef.delete(),
    newTriggerRef.delete(),
    newReviewRef.delete(),
    ...restoredReviews.docs.map((review) => review.ref.delete()),
  ]);
});

test("scraper events create one draft and wait for admin approval", async () => {
  const db = getFirestore();
  const state = uniqueId("state");
  const sourceUrl = `https://example.test/${state}`;
  const path = `_scraper_meta/${state}`;
  const article = {
    title: "Skilled visa nomination update",
    summary: "A migration nomination update for local pipeline testing.",
    link: sourceUrl,
    source: "Test scraper",
    date: new Date().toISOString(),
  };
  const makeEvent = () => ({
    data: {
      before: functionsTest.firestore.makeDocumentSnapshot({}, path),
      after: functionsTest.firestore.makeDocumentSnapshot({ articles: [article] }, path),
    },
    params: { state },
  });

  const firstResult = await onScraperUpdate(makeEvent());
  assert.equal(firstResult.status, "success");
  assert.equal(firstResult.draftsCreated, 1);
  const notificationId = firstResult.drafts[0].notificationId;

  const retryResult = await onScraperUpdate(makeEvent());
  assert.equal(retryResult.draftsCreated, 0);

  const draftRef = db.collection("notifications_draft").doc(notificationId);
  const publishedRef = db.collection("notifications").doc(notificationId);
  const triggerRef = db.collection("fcm_triggers").doc(`approval_${notificationId}_1`);
  const reviewRef = db.collection("notification_reviews").doc(`approved_${notificationId}_1`);
  const [draft, unpublished, untriggered] = await Promise.all([
    draftRef.get(),
    publishedRef.get(),
    triggerRef.get(),
  ]);
  assert.equal(draft.data().status, "draft");
  assert.equal(draft.data().createdBy, "scraper_automation");
  assert.equal(unpublished.exists, false);
  assert.equal(untriggered.exists, false);

  await approveNotification({ data: { notificationId }, auth: adminAuth });
  const [removedDraft, published, trigger, review] = await Promise.all([
    draftRef.get(),
    publishedRef.get(),
    triggerRef.get(),
    reviewRef.get(),
  ]);
  assert.equal(removedDraft.exists, false);
  assert.equal(published.data().sourceUrl, sourceUrl);
  assert.equal(trigger.exists, true);
  assert.equal(review.data().action, "approved");

  await Promise.all([
    publishedRef.delete(),
    triggerRef.delete(),
    reviewRef.delete(),
  ]);
});

test.after(() => functionsTest.cleanup());