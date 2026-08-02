/**
 * MigrateAU — Firebase Cloud Functions
 *
 * processFcmTrigger
 * -----------------
 * Listens to new documents created in the `fcm_triggers` collection
 * (written by the Python scraper) and sends FCM topic notifications
 * using the Firebase Admin SDK (HTTP v1 API — not the deprecated legacy key).
 *
 * Firestore trigger document shape:
 * {
 *   title:      string,   // notification title
 *   body:       string,   // notification body
 *   topics:     string[], // e.g. ["State_VIC", "Occupation_261313"]
 *   articleUrl: string,
 *   createdAt:  Timestamp,
 *   sent:       boolean   // set to true after processing
 * }
 */

const { onDocumentCreated } = require("firebase-functions/v2/firestore");
const { https } = require("firebase-functions/v2");
const { getMessaging } = require("firebase-admin/messaging");
const { getFirestore } = require("firebase-admin/firestore");
const { initializeApp } = require("firebase-admin/app");
const { logger } = require("firebase-functions");
const { createHash } = require("node:crypto");

initializeApp();

/**
 * Map a notification category to the in-app screen it should open.
 * Falls back to the notifications tab for anything unmapped.
 */
function routeForCategory(category) {
  switch ((category || "").toLowerCase()) {
    case "processing time":
    case "processing times":
      return "/processing-times";
    case "visa change":
    case "policy update":
      return "/visas";
    case "skillselect":
    case "invitation round":
    case "rounds":
      return "/(tabs)/rounds";
    default:
      return "/(tabs)/notifications";
  }
}

/**
 * Triggered whenever a new document lands in `fcm_triggers`.
 * Sends one FCM multicast per topic listed in the document,
 * then marks the trigger document as sent.
 */
exports.processFcmTrigger = onDocumentCreated(
  {
    document: "fcm_triggers/{triggerId}",
    region: "us-central1",
  },
  async (event) => {
    const snap = event.data;
    if (!snap) {
      logger.warn("processFcmTrigger: no data in event");
      return;
    }

    const data = snap.data();
    const { title, body, topics, articleUrl, sent, route, id: notificationId } = data;

    // Guard — skip if already processed (e.g. function retry)
    if (sent === true) {
      logger.info(`Trigger ${event.params.triggerId} already sent — skipping`);
      return;
    }

    if (!event.params.triggerId.startsWith("approval_")) {
      logger.warn(`Trigger ${event.params.triggerId} was not created by admin approval — skipping`);
      await snap.ref.update({
        sent: true,
        sentAt: new Date(),
        skippedReason: "admin_approval_required",
      });
      return;
    }

    if (!topics || topics.length === 0) {
      logger.warn("No topics in trigger document — skipping FCM send");
      await snap.ref.update({ sent: true, skippedReason: "no_topics" });
      return;
    }

    if (process.env.FUNCTIONS_EMULATOR === "true") {
      logger.info(`Trigger ${event.params.triggerId} created in emulator — skipping FCM send`);
      try {
        await snap.ref.update({
          sent: true,
          sentAt: new Date(),
          skippedReason: "functions_emulator",
        });
      } catch (error) {
        if (error?.code !== 5) throw error;
        logger.info(`Trigger ${event.params.triggerId} was removed before emulator acknowledgement`);
      }
      return;
    }

    const messaging = getMessaging();
    const errors = [];

    // Send one message per topic (FCM HTTP v1 API — topic send)
    for (const topic of topics) {
      const message = {
        topic,
        notification: {
          title: title ?? "MigrateAU Update",
          body: body ?? "New migration news available.",
        },
        data: {
          route: route ?? "/(tabs)/notifications",
          url: articleUrl ?? "",
          notificationId: notificationId ?? "",
          click_action: "FLUTTER_NOTIFICATION_CLICK",
        },
        android: {
          notification: {
            channelId: "migration_news",
            priority: "high",
            defaultSound: true,
          },
        },
        apns: {
          payload: {
            aps: {
              sound: "default",
              badge: 1,
            },
          },
        },
      };

      try {
        const response = await messaging.send(message);
        logger.info(`FCM sent to topic '${topic}': messageId=${response}`);
      } catch (err) {
        logger.error(`FCM failed for topic '${topic}':`, err);
        errors.push({ topic, error: err.message });
      }
    }

    // Mark trigger as processed
    await snap.ref.update({
      sent: true,
      sentAt: new Date(),
      errors: errors.length > 0 ? errors : null,
    });
  }
);

// ─────────────────────────────────────────────────────────────────────────────
// ADMIN NOTIFICATION MANAGEMENT (Two-Stage Pipeline)
// ─────────────────────────────────────────────────────────────────────────────

function callablePayload(request) {
  return request?.data && typeof request.data === "object" ? request.data : {};
}

function requireAdmin(request) {
  const uid = request.auth?.uid;
  if (!uid) {
    throw new https.HttpsError("unauthenticated", "User must be authenticated");
  }
  if (request.auth?.token?.admin !== true) {
    throw new https.HttpsError("permission-denied", "Admin access required");
  }
  return uid;
}

function cleanRequiredText(value, field, maxLength) {
  if (typeof value !== "string" || !value.trim()) {
    throw new https.HttpsError("invalid-argument", `${field} is required`);
  }
  const cleaned = value.trim();
  if (cleaned.length > maxLength) {
    throw new https.HttpsError("invalid-argument", `${field} must be ${maxLength} characters or fewer`);
  }
  return cleaned;
}

function cleanOptionalText(value, field, maxLength) {
  if (value === undefined) return undefined;
  return cleanRequiredText(value, field, maxLength);
}

function rethrowCallableError(err, fallback) {
  if (err instanceof https.HttpsError) throw err;
  throw new https.HttpsError("internal", err?.message || fallback);
}

function optionalTrimmedText(value, maxLength) {
  if (typeof value !== "string") return undefined;
  const cleaned = value.trim();
  if (!cleaned) return undefined;
  if (cleaned.length > maxLength) {
    throw new https.HttpsError("invalid-argument", `Value must be ${maxLength} characters or fewer`);
  }
  return cleaned;
}

function getContentChangeDraftId(changeId, changeData) {
  if (typeof changeData?.notificationDraftId === "string" && changeData.notificationDraftId.trim()) {
    return changeData.notificationDraftId.trim();
  }
  const fingerprint = createHash("sha256")
    .update(`${changeData?.sourceId || changeData?.source || "unknown"}|${changeData?.title || changeId}|${changeData?.sourceUrl || ""}`)
    .digest("hex")
    .slice(0, 24);
  return `automation-${fingerprint}`;
}

function buildNotificationDraftFromContentChange(changeId, changeData, draftId, approvedAt, uid) {
  const sourceUrl = optionalTrimmedText(changeData?.sourceUrl, 2000) || "";
  const draft = {
    id: draftId,
    title: cleanRequiredText(changeData?.title, "title", 100),
    body: cleanRequiredText(changeData?.body || changeData?.summary || "Migration update detected for review.", "body", 500),
    category: cleanRequiredText(changeData?.category || changeData?.contentType || "Update", "category", 80),
    source: optionalTrimmedText(changeData?.sourceId || changeData?.source, 160) || "scraper_automation",
    requestedTopic: optionalTrimmedText(changeData?.requestedTopic, 160) || "au_migration",
    sourceUrl,
    url: sourceUrl,
    status: "draft",
    createdAt: changeData?.createdAt || approvedAt,
    timestamp: changeData?.createdAt || approvedAt,
    createdBy: "content_change_approval",
    contentChangeId: changeId,
    contentApprovedAt: approvedAt,
    contentApprovedBy: uid,
    contentChangeStatus: "approved",
  };
  const state = optionalTrimmedText(changeData?.state, 32);
  if (state) {
    draft.state = state;
  }
  return draft;
}

function buildContentChangeHistory(action, changeId, changeData, reviewedAt, reviewedBy, extras = {}) {
  return {
    changeId,
    action,
    status: action === "approved" ? "approved" : "rejected",
    contentType: changeData?.contentType || "unknown",
    title: changeData?.title || "",
    summary: changeData?.summary || "",
    sourceUrl: changeData?.sourceUrl || "",
    category: changeData?.category || "",
    currentValue: changeData?.currentValue || null,
    detectedValue: changeData?.detectedValue || null,
    createdAt: changeData?.createdAt || null,
    reviewedAt,
    reviewedBy,
    ...extras,
  };
}

function extractVisaFeeSubclass(changeData) {
  const subclass = optionalTrimmedText(changeData?.subclass, 32);
  if (subclass) return subclass;
  const sourceId = optionalTrimmedText(changeData?.sourceId, 160);
  const sourceMatch = sourceId?.match(/visa_fee_(\d+)/i);
  if (sourceMatch) return sourceMatch[1];
  const title = optionalTrimmedText(changeData?.title, 160);
  const titleMatch = title?.match(/\bSC\s+(\d+)\b/i);
  return titleMatch ? titleMatch[1] : undefined;
}

function normalizeFeeMatch(match) {
  return match
    .replace(/\s+/g, " ")
    .replace(/^AUD\s*(?!\$)/i, "AUD $")
    .replace(/^AUD\s+\$/i, "AUD $")
    .replace(/^(\$)/, "AUD $")
    .trim();
}

function extractVisaFeeValue(rawValue) {
  if (typeof rawValue !== "string") return undefined;
  const compact = rawValue.replace(/\s+/g, " ").trim();
  if (!compact) return undefined;
  if (/no charge/i.test(compact)) return "No charge";

  const audMatches = compact.match(/AUD\s*\$?\s*\d[\d,]*(?:\.\d{2})?(?:\s*[–-]\s*\$?\d[\d,]*(?:\.\d{2})?)?(?:\s*\([^)]*\))?/gi);
  if (audMatches?.length) {
    return [...new Set(audMatches.map(normalizeFeeMatch))].join(" / ");
  }

  const dollarMatches = compact.match(/\$\s*\d[\d,]*(?:\.\d{2})?(?:\s*[–-]\s*\$?\d[\d,]*(?:\.\d{2})?)?(?:\s*\([^)]*\))?/g);
  if (dollarMatches?.length) {
    return [...new Set(dollarMatches.map(normalizeFeeMatch))].join(" / ");
  }

  return undefined;
}

function buildVisaFeeEntriesFromChange(changeId, changeData) {
  if (Array.isArray(changeData?.fees) && changeData.fees.length > 0) {
    return changeData.fees.map((entry, index) => ({
      subclass: cleanRequiredText(entry?.subclass, `fees[${index}].subclass`, 32),
      fee: cleanRequiredText(entry?.fee, `fees[${index}].fee`, 120),
      note: optionalTrimmedText(entry?.note, 500),
    }));
  }

  const subclass = extractVisaFeeSubclass(changeData);
  const fee = cleanRequiredText(
    changeData?.detectedFee ||
      extractVisaFeeValue(changeData?.detectedValue) ||
      extractVisaFeeValue(changeData?.summary) ||
      extractVisaFeeValue(changeData?.body) ||
      extractVisaFeeValue(changeData?.title),
    "detected fee",
    120
  );

  if (!subclass) {
    throw new https.HttpsError("failed-precondition", `Visa fee change ${changeId} is missing a visa subclass`);
  }

  return [{
    subclass,
    fee,
    note: optionalTrimmedText(changeData?.summary, 500),
  }];
}

const { getStorage } = require("firebase-admin/storage");

async function persistVisaFees(db, uid, fees, snapshotDate, extraHistory = {}) {
  if (!Array.isArray(fees) || fees.length === 0) {
    throw new https.HttpsError("invalid-argument", "fees must be a non-empty array");
  }

  for (const entry of fees) {
    cleanRequiredText(entry?.subclass, "subclass", 32);
    cleanRequiredText(entry?.fee, "fee", 120);
    if (entry?.note !== undefined) {
      cleanRequiredText(entry.note, "note", 500);
    }
  }

  const now = new Date().toISOString();
  const date = snapshotDate || now.slice(0, 10);
  const batch = db.batch();

  for (const entry of fees) {
    const ref = db.collection("visa_fees").doc(entry.subclass);
    batch.set(ref, {
      subclass: entry.subclass,
      fee: entry.fee,
      note: entry.note || null,
      updatedAt: now,
      updatedBy: uid,
    });
  }
  await batch.commit();

  const snapshot = { snapshotDate: date, items: fees };
  const bucket = getStorage().bucket();
  const file = bucket.file("visa-fees.json");
  await file.save(JSON.stringify(snapshot, null, 2), {
    contentType: "application/json",
    metadata: {
      cacheControl: "public, max-age=3600, stale-while-revalidate=86400",
    },
  });
  await file.makePublic();

  await db.collection("fee_update_history").add({
    updatedAt: now,
    updatedBy: uid,
    snapshotDate: date,
    count: fees.length,
    ...extraHistory,
  });

  logger.info(`[updateVisaFees] ${fees.length} fees updated by ${uid}`);
  return { success: true, count: fees.length, snapshotDate: date };
}

/**
 * approveNotification - Move notification from draft to published and send FCM
 * 
 * Request: { notificationId, editedTitle?, editedBody? }
 * Returns: { success, message, notificationId }
 */
exports.approveNotification = https.onCall({ cors: true }, async (request) => {
  const uid = await requireAdmin(request);
  const payload = callablePayload(request);
  const notificationId = cleanRequiredText(payload.notificationId, "notificationId", 160);
  const editedTitle = cleanOptionalText(payload.editedTitle, "title", 100);
  const editedBody = cleanOptionalText(payload.editedBody, "body", 500);

  const db = getFirestore();

  try {
    const draftRef = db.collection("notifications_draft").doc(notificationId);
    const publishedRef = db.collection("notifications").doc(notificationId);

    const result = await db.runTransaction(async (transaction) => {
      const [draftSnap, publishedSnap] = await Promise.all([
        transaction.get(draftRef),
        transaction.get(publishedRef),
      ]);

      if (!draftSnap.exists) {
        if (publishedSnap.exists) return { alreadyPublished: true };
        throw new https.HttpsError("not-found", "Draft notification not found");
      }

      const draftData = draftSnap.data();
      if (draftData.contentChangeId) {
        const contentChangeRef = db.collection("pending_content_changes").doc(draftData.contentChangeId);
        const contentChangeSnap = await transaction.get(contentChangeRef);
        if (!contentChangeSnap.exists) {
          throw new https.HttpsError(
            "failed-precondition",
            "This notification is linked to a content change that has not been approved yet"
          );
        }
        const contentChangeStatus = contentChangeSnap.data()?.status;
        if (contentChangeStatus !== "approved") {
          throw new https.HttpsError(
            "failed-precondition",
            "Approve the linked content change before publishing this notification"
          );
        }
      }
      const title = editedTitle ?? cleanRequiredText(draftData.title, "title", 100);
      const body = editedBody ?? cleanRequiredText(draftData.body, "body", 500);
      const category = cleanRequiredText(draftData.category, "category", 80);
      const approvalGeneration = Number.isInteger(draftData.approvalGeneration)
        ? draftData.approvalGeneration
        : 1;
      const approvedAt = new Date().toISOString();
      const triggerRef = db.collection("fcm_triggers")
        .doc(`approval_${notificationId}_${approvalGeneration}`);
      const reviewRef = db.collection("notification_reviews")
        .doc(`approved_${notificationId}_${approvalGeneration}`);
      const publishedData = {
        ...draftData,
        id: notificationId,
        title,
        body,
        category,
        status: "published",
        read: false,
        approvalGeneration,
        approvedAt,
        approvedBy: uid,
      };
      const topics = ["au_migration"];
      if (publishedData.state && publishedData.state !== "FED") {
        topics.push(`state_${publishedData.state}`);
      }

      transaction.set(publishedRef, publishedData);
      transaction.set(triggerRef, {
        title,
        body,
        topics,
        articleUrl: publishedData.url || publishedData.sourceUrl || "",
        route: routeForCategory(category),
        createdAt: new Date(),
        sent: false,
      });
      transaction.set(reviewRef, {
        notificationId,
        action: "approved",
        approver: uid,
        timestamp: approvedAt,
        editedTitle: editedTitle ?? null,
        editedBody: editedBody ?? null,
      });
      transaction.delete(draftRef);
      return { alreadyPublished: false };
    });

    return {
      success: true,
      message: result.alreadyPublished
        ? "Notification was already published"
        : "Notification published successfully",
      notificationId,
      alreadyPublished: result.alreadyPublished,
    };
  } catch (err) {
    logger.error(`Error approving notification ${notificationId}:`, err);
    rethrowCallableError(err, "Approval failed");
  }
});

/**
 * approveContentChange - Approve a detected scraper content change.
 *
 * Request: { changeId, notes? }
 * Returns: { success, message, changeId, draftCreated }
 */
exports.approveContentChange = https.onCall({ cors: true }, async (request) => {
  const uid = requireAdmin(request);
  const payload = callablePayload(request);
  const changeId = cleanRequiredText(payload.changeId, "changeId", 160);
  const notes = payload.notes === undefined
    ? undefined
    : cleanRequiredText(payload.notes, "notes", 500);

  const db = getFirestore();
  const changeRef = db.collection("pending_content_changes").doc(changeId);

  try {
    const initialSnap = await changeRef.get();
    if (!initialSnap.exists) {
      throw new https.HttpsError("not-found", "Content change not found");
    }

    const initialData = initialSnap.data();
    if (initialData.status === "approved") {
      return {
        success: true,
        message: "Content change was already approved",
        changeId,
        draftCreated: false,
        alreadyApproved: true,
      };
    }
    if (initialData.status === "rejected") {
      throw new https.HttpsError("failed-precondition", "Content change has already been rejected");
    }

    const reviewedAt = new Date().toISOString();
    let appliedFeesCount = 0;
    if (initialData.contentType === "visa_fees") {
      const fees = buildVisaFeeEntriesFromChange(changeId, initialData);
      await persistVisaFees(
        db,
        uid,
        fees,
        reviewedAt.slice(0, 10),
        { source: "content_change_approval", contentChangeId: changeId }
      );
      appliedFeesCount = fees.length;
    }

    const historyRef = db.collection("content_change_history").doc();
    const result = await db.runTransaction(async (transaction) => {
      const freshSnap = await transaction.get(changeRef);
      if (!freshSnap.exists) {
        throw new https.HttpsError("not-found", "Content change not found");
      }

      const changeData = freshSnap.data();
      if (changeData.status === "approved") {
        return { alreadyApproved: true, draftCreated: false, draftId: null, contentType: changeData.contentType };
      }
      if (changeData.status === "rejected") {
        throw new https.HttpsError("failed-precondition", "Content change has already been rejected");
      }

      const updatePayload = {
        status: "approved",
        reviewedAt,
        reviewedBy: uid,
        notes: notes || null,
      };
      transaction.update(changeRef, updatePayload);

      let draftCreated = false;
      let draftId = null;
      if (changeData.contentType !== "visa_fees") {
        draftId = getContentChangeDraftId(changeId, changeData);
        const draftRef = db.collection("notifications_draft").doc(draftId);
        const draftSnap = await transaction.get(draftRef);
        if (draftSnap.exists) {
          transaction.set(draftRef, {
            contentChangeId: changeId,
            contentApprovedAt: reviewedAt,
            contentApprovedBy: uid,
            contentChangeStatus: "approved",
          }, { merge: true });
        } else {
          transaction.set(
            draftRef,
            buildNotificationDraftFromContentChange(changeId, changeData, draftId, reviewedAt, uid)
          );
          draftCreated = true;
        }
      }

      transaction.set(
        historyRef,
        buildContentChangeHistory("approved", changeId, changeData, reviewedAt, uid, {
          notes: notes || null,
          notificationDraftId: draftId,
          notificationDraftCreated: draftCreated,
          appliedFeesCount,
        })
      );

      return {
        alreadyApproved: false,
        draftCreated,
        draftId,
        contentType: changeData.contentType,
      };
    });

    return {
      success: true,
      message: result.alreadyApproved
        ? "Content change was already approved"
        : result.contentType === "visa_fees"
          ? "Content change approved and visa fees updated"
          : result.draftCreated
            ? "Content change approved and notification draft created"
            : "Content change approved",
      changeId,
      draftCreated: result.draftCreated,
      draftId: result.draftId,
      alreadyApproved: result.alreadyApproved,
      appliedFeesCount,
    };
  } catch (err) {
    logger.error(`Error approving content change ${changeId}:`, err);
    rethrowCallableError(err, "Content change approval failed");
  }
});

/**
 * rejectContentChange - Reject a detected scraper content change.
 *
 * Request: { changeId, reason? }
 * Returns: { success, message, changeId, draftRemoved }
 */
exports.rejectContentChange = https.onCall({ cors: true }, async (request) => {
  const uid = requireAdmin(request);
  const payload = callablePayload(request);
  const changeId = cleanRequiredText(payload.changeId, "changeId", 160);
  const reason = payload.reason === undefined
    ? "Rejected by administrator"
    : cleanRequiredText(payload.reason, "reason", 500);

  const db = getFirestore();
  const changeRef = db.collection("pending_content_changes").doc(changeId);
  const historyRef = db.collection("content_change_history").doc();

  try {
    const result = await db.runTransaction(async (transaction) => {
      const changeSnap = await transaction.get(changeRef);
      if (!changeSnap.exists) {
        throw new https.HttpsError("not-found", "Content change not found");
      }

      const changeData = changeSnap.data();
      if (changeData.status === "rejected") {
        return { alreadyRejected: true, draftRemoved: false };
      }
      if (changeData.status === "approved") {
        throw new https.HttpsError("failed-precondition", "Approved content changes cannot be rejected");
      }

      const reviewedAt = new Date().toISOString();
      transaction.update(changeRef, {
        status: "rejected",
        reviewedAt,
        reviewedBy: uid,
        reason,
      });

      let draftRemoved = false;
      const draftId = getContentChangeDraftId(changeId, changeData);
      const draftRef = db.collection("notifications_draft").doc(draftId);
      const draftSnap = await transaction.get(draftRef);
      if (draftSnap.exists) {
        transaction.delete(draftRef);
        draftRemoved = true;
      }

      transaction.set(
        historyRef,
        buildContentChangeHistory("rejected", changeId, changeData, reviewedAt, uid, {
          reason,
          notificationDraftId: draftId,
          notificationDraftRemoved: draftRemoved,
        })
      );

      return { alreadyRejected: false, draftRemoved };
    });

    return {
      success: true,
      message: result.alreadyRejected
        ? "Content change was already rejected"
        : "Content change rejected",
      changeId,
      draftRemoved: result.draftRemoved,
      alreadyRejected: result.alreadyRejected,
    };
  } catch (err) {
    logger.error(`Error rejecting content change ${changeId}:`, err);
    rethrowCallableError(err, "Content change rejection failed");
  }
});

/**
 * rejectNotification - Delete from draft and log rejection
 * 
 * Request: { notificationId, reason }
 * Returns: { success, message }
 */
exports.rejectNotification = https.onCall({ cors: true }, async (request) => {
  const uid = await requireAdmin(request);
  const payload = callablePayload(request);
  const notificationId = cleanRequiredText(payload.notificationId, "notificationId", 160);
  const reason = payload.reason === undefined
    ? "No reason provided"
    : cleanRequiredText(payload.reason, "reason", 500);

  const db = getFirestore();

  try {
    const draftRef = db.collection("notifications_draft").doc(notificationId);
    const reviewRef = db.collection("notification_reviews").doc(`rejected_${notificationId}`);
    await db.runTransaction(async (transaction) => {
      const draftSnap = await transaction.get(draftRef);
      if (!draftSnap.exists) {
        throw new https.HttpsError("not-found", "Draft notification not found");
      }
      transaction.set(reviewRef, {
        notificationId,
        action: "rejected",
        rejector: uid,
        timestamp: new Date().toISOString(),
        rejectionReason: reason,
      });
      transaction.delete(draftRef);
    });

    return {
      success: true,
      message: "Notification rejected and removed from draft",
      notificationId,
    };
  } catch (err) {
    logger.error(`Error rejecting notification ${notificationId}:`, err);
    rethrowCallableError(err, "Rejection failed");
  }
});

/**
 * archiveNotification - Remove a published notification from the public feed
 * while preserving the notification and an audit record.
 *
 * Request: { notificationId, reason? }
 * Returns: { success, message, notificationId, alreadyArchived }
 */
exports.archiveNotification = https.onCall({ cors: true }, async (request) => {
  const uid = await requireAdmin(request);
  const payload = callablePayload(request);
  const notificationId = cleanRequiredText(payload.notificationId, "notificationId", 160);
  const reason = payload.reason === undefined
    ? "Archived by administrator"
    : cleanRequiredText(payload.reason, "reason", 500);

  const db = getFirestore();

  try {
    const publishedRef = db.collection("notifications").doc(notificationId);
    const archivedRef = db.collection("notifications_archived").doc(notificationId);
    const reviewRef = db.collection("notification_reviews").doc(`archived_${notificationId}`);
    const result = await db.runTransaction(async (transaction) => {
      const [publishedSnap, archivedSnap] = await Promise.all([
        transaction.get(publishedRef),
        transaction.get(archivedRef),
      ]);
      if (!publishedSnap.exists) {
        if (archivedSnap.exists) return { alreadyArchived: true };
        throw new https.HttpsError("not-found", "Published notification not found");
      }

      const publishedData = publishedSnap.data();
      if (publishedData.status && publishedData.status !== "published" && publishedData.status !== "archived") {
        throw new https.HttpsError("failed-precondition", "Notification is not published");
      }

      const archivedAt = new Date().toISOString();
      transaction.set(archivedRef, {
        ...publishedData,
        id: notificationId,
        status: "archived",
        archivedAt,
        archivedBy: uid,
        archiveReason: reason,
      });
      transaction.set(reviewRef, {
        notificationId,
        action: "archived",
        archiver: uid,
        timestamp: archivedAt,
        archiveReason: reason,
      });
      transaction.delete(publishedRef);
      return { alreadyArchived: false };
    });

    return {
      success: true,
      message: result.alreadyArchived
        ? "Notification was already archived"
        : "Notification archived successfully",
      notificationId,
      alreadyArchived: result.alreadyArchived,
    };
  } catch (err) {
    logger.error(`Error archiving notification ${notificationId}:`, err);
    rethrowCallableError(err, "Archive failed");
  }
});

/**
 * restoreArchivedNotification - Move an archived notification back to drafts.
 *
 * Request: { notificationId }
 * Returns: { success, message, notificationId, alreadyRestored }
 */
exports.restoreArchivedNotification = https.onCall({ cors: true }, async (request) => {
  const uid = await requireAdmin(request);
  const payload = callablePayload(request);
  const notificationId = cleanRequiredText(payload.notificationId, "notificationId", 160);

  const db = getFirestore();

  try {
    const archivedRef = db.collection("notifications_archived").doc(notificationId);
    const draftRef = db.collection("notifications_draft").doc(notificationId);
    const reviewRef = db.collection("notification_reviews").doc();
    const result = await db.runTransaction(async (transaction) => {
      const [archivedSnap, draftSnap] = await Promise.all([
        transaction.get(archivedRef),
        transaction.get(draftRef),
      ]);
      if (!archivedSnap.exists) {
        if (draftSnap.exists) return { alreadyRestored: true };
        throw new https.HttpsError("not-found", "Archived notification not found");
      }
      if (draftSnap.exists) {
        throw new https.HttpsError("already-exists", "A draft with this ID already exists");
      }

      const archivedData = archivedSnap.data();
      const {
        approvedAt,
        approvedBy,
        archivedAt,
        archivedBy,
        archiveReason,
        read,
        ...draftBase
      } = archivedData;
      const restoredAt = new Date().toISOString();
      transaction.set(draftRef, {
        ...draftBase,
        id: notificationId,
        status: "draft",
        approvalGeneration: Number.isInteger(archivedData.approvalGeneration)
          ? archivedData.approvalGeneration + 1
          : 2,
        restoredAt,
        restoredBy: uid,
        updatedAt: restoredAt,
        updatedBy: uid,
      });
      transaction.set(reviewRef, {
        notificationId,
        action: "restored",
        restorer: uid,
        timestamp: restoredAt,
      });
      transaction.delete(archivedRef);
      return { alreadyRestored: false };
    });

    return {
      success: true,
      message: result.alreadyRestored
        ? "Notification was already restored"
        : "Notification restored to drafts",
      notificationId,
      alreadyRestored: result.alreadyRestored,
    };
  } catch (err) {
    logger.error(`Error restoring notification ${notificationId}:`, err);
    rethrowCallableError(err, "Restore failed");
  }
});

/**
 * editDraftNotification - Edit a draft notification before approval
 * 
 * Request: { notificationId, title?, body?, category? }
 * Returns: { success, message, notification }
 */
exports.editDraftNotification = https.onCall({ cors: true }, async (request) => {
  const uid = await requireAdmin(request);
  const payload = callablePayload(request);
  const notificationId = cleanRequiredText(payload.notificationId, "notificationId", 160);
  const title = cleanOptionalText(payload.title, "title", 100);
  const body = cleanOptionalText(payload.body, "body", 500);
  const category = cleanOptionalText(payload.category, "category", 80);
  if (title === undefined && body === undefined && category === undefined) {
    throw new https.HttpsError("invalid-argument", "At least one editable field is required");
  }

  const db = getFirestore();

  try {
    const draftRef = db.collection("notifications_draft").doc(notificationId);
    const draftSnap = await draftRef.get();

    if (!draftSnap.exists) {
      throw new https.HttpsError("not-found", "Draft notification not found");
    }

    const updates = {
      updatedAt: new Date().toISOString(),
      updatedBy: uid,
    };

    if (title !== undefined) updates.title = title;
    if (body !== undefined) updates.body = body;
    if (category !== undefined) updates.category = category;

    await draftRef.update(updates);

    const updated = await draftRef.get();

    return {
      success: true,
      message: "Draft updated successfully",
      notification: { id: notificationId, ...updated.data() },
    };
  } catch (err) {
    logger.error(`Error editing draft ${notificationId}:`, err);
    rethrowCallableError(err, "Edit failed");
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// SCRAPER UPDATE HANDLER - Auto-create notifications when scraper finds articles
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Bridges the currently scheduled Python scraper's news archive into the
 * approval queue. The deterministic ID matches state_news_scraper.py.
 */
exports.onNewsArticleCreated = onDocumentCreated(
  {
    document: "news/{articleId}",
    region: "us-central1",
  },
  async (event) => {
    const article = event.data?.data();
    if (!article) return;

    const state = String(article.state || "FED").toUpperCase();
    const articleId = event.params.articleId;
    const notificationId = `scraper-${state.toLowerCase()}-${articleId}`;
    const createdAt = new Date().toISOString();
    const sourceUrl = typeof article.url === "string" ? article.url.trim() : "";
    const draftRef = getFirestore().collection("notifications_draft").doc(notificationId);
    const created = await getFirestore().runTransaction(async (transaction) => {
      const existing = await transaction.get(draftRef);
      if (existing.exists) return false;
      transaction.create(draftRef, {
        id: notificationId,
        title: cleanRequiredText(article.title, "title", 100),
        body: cleanRequiredText(article.summary || "New migration news available", "body", 500),
        category: "News",
        source: article.source || "scraper",
        sourceUrl,
        url: sourceUrl,
        state,
        status: "draft",
        articleDate: article.publishedAt || createdAt,
        createdAt,
        timestamp: createdAt,
        createdBy: "scraper_automation",
        sourceFingerprint: articleId,
      });
      return true;
    });

    logger.info(`[News Archive] ${created ? "Created" : "Reused"} approval draft ${notificationId}`);
  },
);

/**
 * onScraperUpdate - Triggers when scraper metadata updates
 * 
 * Creates approval drafts for new migration news articles found by the scraper.
 * 
 * Firestore Path: _scraper_meta/{state}
 * 
 * Flow:
 * 1. Detects new articles from scraper
 * 2. Creates a deterministic document in notifications_draft
 * 3. Waits for an administrator to approve or reject it
 */
const { onDocumentWritten } = require("firebase-functions/v2/firestore");

exports.onScraperUpdate = onDocumentWritten(
  {
    document: "_scraper_meta/{state}",
    region: "us-central1",
  },
  async (event) => {
    const state = event.params.state;
    const snap = event.data;
    
    if (!snap) {
      logger.warn(`[Scraper Update] No snap data for state: ${state}`);
      return { status: "no_snap", state };
    }

    try {
      logger.info(`📡 [Scraper Update] Detected update for state: ${state}`, {
        state,
        timestamp: new Date().toISOString(),
      });

      // Get the new data from scraper
      const data = snap.after?.data?.() || snap.data?.();
      if (!data) {
        logger.warn(`⚠️ [Scraper Update] No data for state: ${state}`);
        return { status: "no_data", state };
      }

      // Reprocess today's articles safely; deterministic IDs make retries no-ops.
      const newArticles = data.articles || [];
      let recentArticles = newArticles;
      
      // Filter for today's articles and visa-related content
      const today = new Date().toDateString();
      const visaKeywords = ['visa', 'migration', 'skilled', 'skilled migration', 'nomination', 'pr', 'permanent resident', 'work permit', 'sponsorship', 'SkillSelect', 'points', 'ANZSCO', 'occupation', 'subclass'];
      
      recentArticles = recentArticles.filter(article => {
        // Check if article is from today
        const articleDate = article.date ? new Date(article.date).toDateString() : null;
        if (!articleDate || articleDate !== today) {
          logger.debug(`[Scraper] Skipping article - not from today: ${article.title}`);
          return false;
        }
        
        // Check if article is visa-related
        const titleBody = `${(article.title || '').toLowerCase()} ${(article.summary || '').toLowerCase()} ${(article.description || '').toLowerCase()}`;
        const isVisaRelated = visaKeywords.some(keyword => titleBody.includes(keyword.toLowerCase()));
        if (!isVisaRelated) {
          logger.debug(`[Scraper] Skipping article - not visa-related: ${article.title}`);
          return false;
        }
        
        return true;
      });
      
      logger.info(
        `🔍 [Scraper Update] Found ${recentArticles.length} new visa-related articles for ${state} (from today)`,
        { state, totalArticles: newArticles.length, filteredCount: recentArticles.length }
      );

      const db = getFirestore();
      const drafts = [];
      const errors = [];

      // Create one stable draft per source article. Approval is the only publish path.
      for (const article of recentArticles) {
        try {
          const articleLink = (article.link && article.link.trim()) ? article.link.trim() : null;
          const fingerprint = createHash("sha256")
            .update(`${state}|${articleLink || article.title || "untitled"}|${article.date || "undated"}`)
            .digest("hex")
            .slice(0, 24);
          const notificationId = `scraper-${String(state).toLowerCase()}-${fingerprint}`;
          const draftRef = db.collection("notifications_draft").doc(notificationId);
          const createdAt = new Date().toISOString();

          const draft = {
            id: notificationId,
            title: article.title || `New ${state} Migration Update`,
            body: article.summary || article.description || "New migration news available",
            category: "News",
            source: article.source || "scraper",
            sourceUrl: articleLink || "",
            url: articleLink || "",
            state,
            status: "draft",
            articleDate: article.date || createdAt,
            createdAt,
            timestamp: createdAt,
            createdBy: "scraper_automation",
            hasValidSourceUrl: !!articleLink,
            sourceFingerprint: fingerprint,
          };

          const created = await db.runTransaction(async (transaction) => {
            const existing = await transaction.get(draftRef);
            if (existing.exists) return false;
            transaction.create(draftRef, draft);
            return true;
          });

          if (created) {
            drafts.push({ notificationId, title: draft.title });
            logger.info(`[Scraper Update] Created approval draft: ${notificationId}`);
          } else {
            logger.info(`[Scraper Update] Draft already exists: ${notificationId}`);
          }

        } catch (articleError) {
          logger.error(
            `❌ [Scraper Update] Error processing article for ${state}`,
            { error: articleError }
          );
          errors.push(articleError.message);
        }
      }

      logger.info(
        `🎉 [Scraper Update] Complete for ${state}`,
        { 
          state,
          draftsCreated: drafts.length,
          errors: errors.length > 0 ? errors : null,
          timestamp: new Date().toISOString(),
        }
      );

      return {
        status: "success",
        state,
        draftsCreated: drafts.length,
        drafts,
        errors: errors.length > 0 ? errors : null,
      };

    } catch (error) {
      logger.error(
        `❌ [Scraper Update] Fatal error for state ${state}`,
        { error, state }
      );
      
      return {
        status: "error",
        state,
        error: error.message,
      };
    }
  }
);

// ─────────────────────────────────────────────────────────────────────────────
// ARIA CHAT — AI-Powered Visa Consultant with Response Caching
// ─────────────────────────────────────────────────────────────────────────────

const { onRequest } = require("firebase-functions/v2/https");
const { defineString } = require("firebase-functions/params");
const { GoogleGenerativeAI } = require("@google/generative-ai");

const GEMINI_API_KEY = defineString("GEMINI_API_KEY");

// Response cache (memory + Firestore)
const responseCache = new Map();

// Pre-populate cache with common questions (key optimization)
const COMMON_RESPONSES = {
  "how do i reach 95 points": "🏆 **Reaching 95+ Points for SC 189**\n\n| Factor | Max Points |\n|--------|------------|\n| Age (25-32) | 30 |\n| English (PTE 79+/IELTS 8+) | 20 |\n| Work Experience (8+ yrs overseas) | 15 |\n| Australian Work Exp (3+ yrs) | 10 |\n| Education (PhD) | 20 |\n| Specialist Education | 10 |\n| NAATI/CCL | 5 |\n| Partner Skills | 10 |\n| State Nomination (190) | 5 |\n\n🚀 **Strategy:**\n1. Max English score (PTE Academic is fastest)\n2. Get NAATI/CCL credential (+5 easy points)\n3. Consider 190 state nomination (+5)\n4. Professional Year if eligible (+5)\n\n📍 Stage 2: Expression — Submit EOI with highest possible points\n\n⚖️ Consult MARA for formal advice.",
  "how many points do i need": "🏆 **Points Required for Skilled Visas:**\n\n| Visa | Min Points | Competitive |\n|------|-----------|-------------|\n| SC 189 | 65 | 80-95+ |\n| SC 190 | 65 (incl. 5 state) | 70-85 |\n| SC 491 | 65 (incl. 15 regional) | 65-75 |\n\n📊 Recent 189 rounds: minimum 65-80 points depending on occupation.\n\n🚀 Next Step: Use the Points Calculator in the app to estimate your score.\n\n⚖️ Consult MARA for formal advice.",
  "what is skills assessment": "📋 **Skills Assessment** is a mandatory evaluation proving your qualifications match your nominated ANZSCO occupation.\n\n**Key Bodies:**\n- ACS (IT occupations)\n- Engineers Australia (Engineering)\n- VETASSESS (General professional)\n- TRA (Trades)\n- AHPRA (Health/Medical)\n\n**Process:** Submit qualifications + work references → 6-12 weeks → Outcome letter\n\n📍 Stage 1: Preparation\n🚀 Next Step: Identify your assessing authority in the Skill Assessment tab.\n\n⚖️ Consult MARA for formal advice.",
  "what is anzsco": "ANZSCO is the Australian & New Zealand Standard Classification of Occupations. It's used to identify your occupation for visa purposes. Example: 261313 = Software Developer. You need a positive skills assessment in your ANZSCO code.\n\n🚀 Next Step: Search your occupation in the Occupations tab.\n\n⚖️ Consult MARA for formal advice.",
  "what visa should i apply for": "Main skilled visas:\n- **189** (65+ points, independent, fastest to PR)\n- **190** (60+ points, state-sponsored, +5 points)\n- **491** (45+ points, regional, provisional 5yr)\n\nCheck your points first, then choose based on your score and location preference.\n\n📍 Stage 2: Expression\n🚀 Next Step: Use the Points Calculator to see where you stand.\n\n⚖️ Consult MARA for formal advice.",
  "how do i get pr": "🇦🇺 **5-Stage Path to PR:**\n\n1. **Preparation** — Skills assessment + English test\n2. **Expression** — Submit EOI on SkillSelect\n3. **Invitation** — Receive ITA (Invitation to Apply)\n4. **Lodgement** — Submit visa application + docs\n5. **Grant** — PR visa granted!\n\n⏱️ Timeline: 12-24 months typical\n\n📍 Stage 1: Preparation\n🚀 Next Step: Get your skills assessed and take an English test.\n\n⚖️ Consult MARA for formal advice.",
  "hi": "G'day! 🇦🇺 I'm Aria, your Australian migration consultant. Ask me about:\n\n• Visa options (189/190/491)\n• Points calculation\n• ANZSCO codes & skills assessment\n• English tests (IELTS, PTE)\n• State nominations\n\nWhat can I help you with?",
  "hello": "G'day! 🇦🇺 I'm Aria, your Australian migration consultant. Ask me about:\n\n• Visa options (189/190/491)\n• Points calculation\n• ANZSCO codes & skills assessment\n• English tests (IELTS, PTE)\n• State nominations\n\nWhat can I help you with?",
  "hey": "G'day! 🇦🇺 I'm Aria, your Australian migration consultant. Ask me about:\n\n• Visa options (189/190/491)\n• Points calculation\n• ANZSCO codes & skills assessment\n• English tests (IELTS, PTE)\n• State nominations\n\nWhat can I help you with?",
};

// Pre-populate cache on function initialization
for (const [key, response] of Object.entries(COMMON_RESPONSES)) {
  responseCache.set(key, response);
}


const ARIA_SYSTEM_PROMPT = `You are Aria 🇦🇺 — Senior Australian Migration Consultant AI.

## SCOPE: Australian Migration Only
- Skilled visas: 189, 190, 491, 482, 186, 485, 494
- Family visas: 820/801, 309/100, 143
- Student visa 500, Visitor visa 600
- Points system, ANZSCO codes, Skills assessments
- English tests (IELTS, PTE, TOEFL, CAE, OET)
- State nominations & invitation trends
- EOI strategy, document validity, age-bracket points

Off-topic: "I'm focused on Australian migration."

## GOLDEN PATH (5 Stages)
1. **PREPARATION** — Skills assessment, English test, docs
2. **EXPRESSION** — EOI, points optimisation
3. **LODGEMENT** — Visa application
4. **SETTLEMENT** — Arrival, PR obligations
5. **CITIZENSHIP** — Eligibility, test, passport

Always tell user: "📍 Stage X: [Name]" and "🚀 Next Step: [action]"

Use Markdown, tables, bullet points.
End with: "⚖️ Consult MARA for formal advice."`;

// Generate cache key (more aggressive normalization)
function getCacheKey(message) {
  return message
    .trim()
    .toLowerCase()
    .replace(/[?!.,"'+\-()\[\]{}:;]/g, '') // Remove punctuation including +
    .replace(/\s+/g, " ")
    .substring(0, 100);
}

// Check cache
async function getCachedResponse(cacheKey) {
  if (responseCache.has(cacheKey)) {
    logger.info("[ariaChat] Cache HIT (memory): " + cacheKey);
    return responseCache.get(cacheKey);
  }

  try {
    const db = getFirestore();
    const doc = await db.collection("aria_cache").doc(cacheKey).get();
    if (doc.exists && doc.data()?.reply) {
      const cached = doc.data().reply;
      responseCache.set(cacheKey, cached);
      logger.info("[ariaChat] Cache HIT (firestore): " + cacheKey);
      return cached;
    }
  } catch (err) {
    logger.warn("[ariaChat] Firestore cache lookup failed:", err.message);
  }

  return null;
}

// Save response to cache (fire-and-forget)
async function cacheResponse(cacheKey, reply) {
  // Save to memory immediately
  responseCache.set(cacheKey, reply);

  // Save to Firestore asynchronously (don't await)
  try {
    const db = getFirestore();
    // Fire and forget - don't await, just start the write
    db.collection("aria_cache")
      .doc(cacheKey)
      .set(
        {
          reply,
          createdAt: new Date(),
          ttl: Math.floor(Date.now() / 1000) + 86400 * 30,
        },
        { merge: true }
      )
      .catch(err =>
        logger.warn("[ariaChat] Firestore cache save failed:", err.message)
      );
  } catch (err) {
    logger.warn("[ariaChat] Failed to initialize Firestore cache:", err.message);
  }
}

// Aria Chat endpoint
exports.ariaChat = onRequest(
  {
    region: "us-central1",
    cors: true,
    timeoutSeconds: 60,
    memory: "512MiB",
  },
  async (req, res) => {
    if (req.method === "OPTIONS") {
      res.status(200).send("");
      return;
    }

    if (req.method !== "POST") {
      res.status(405).json({ error: "Method not allowed" });
      return;
    }

    try {
      const { message, history } = req.body || {};

      if (!message || typeof message !== "string" || !message.trim()) {
        res.status(400).json({ error: "message required" });
        return;
      }

      const cacheKey = getCacheKey(message);

      // Try cache first
      logger.info("[ariaChat] Checking cache for: " + cacheKey);
      let cachedReply = await getCachedResponse(cacheKey);
      if (cachedReply) {
        return res.status(200).json({ reply: cachedReply });
      }

      logger.info("[ariaChat] API request (not in cache)");

      // Sanitize history
      const chatHistory = (Array.isArray(history) ? history : [])
        .filter(m => m && (m.role === "user" || m.role === "model"))
        .slice(-20)
        .map(m => ({
          role: m.role,
          parts: [{ text: m.text }],
        }));

      try {
        logger.info("[ariaChat] Initializing GoogleGenerativeAI...");
        const apiKey = GEMINI_API_KEY.value();
        if (!apiKey) {
          throw new Error("GEMINI_API_KEY env not set");
        }
        const genAI = new GoogleGenerativeAI(apiKey);

        logger.info("[ariaChat] Creating model: gemini-2.5-flash");
        const model = genAI.getGenerativeModel({
          model: "gemini-2.5-flash",
          systemInstruction: ARIA_SYSTEM_PROMPT,
        });

        logger.info(
          "[ariaChat] Starting chat with " + chatHistory.length + " history messages"
        );

        const chat = model.startChat({ history: chatHistory });
        logger.info("[ariaChat] Calling sendMessage...");

        const result = await chat.sendMessage(message);
        const reply = result.response.text();

        logger.info("[ariaChat] SUCCESS! Reply length: " + reply.length);

        // Cache the response
        await cacheResponse(cacheKey, reply);

        res.status(200).json({ reply });
      } catch (geminiErr) {
        const errorInfo = {
          name: geminiErr?.name || "Unknown",
          message: geminiErr?.message || "No message",
          code: geminiErr?.code || "N/A",
          status: geminiErr?.status || "N/A",
        };

        logger.error("[ariaChat] Gemini API Error:", JSON.stringify(errorInfo));

        // Intelligent fallback
        let fallbackReply;
        const rateLimitError =
          geminiErr?.message?.includes("429") ||
          geminiErr?.message?.includes("depleted");

        if (rateLimitError) {
          fallbackReply = `⚠️ **High Demand Right Now**\n\nAria is helping many users. Here's what you can do immediately:\n\n✅ **Instant Resources:**\n- **Official Portal:** [immi.homeaffairs.gov.au](https://immi.homeaffairs.gov.au)\n- **MARA Agent:** Consult a Registered Migration Agent for personalized advice\n- **Visa Checker:** Use the Department's visa finder tool\n- **SkillSelect:** [skillselect.gov.au](https://skillselect.gov.au) for invitation status\n\n🔄 **Reload in 10-15 seconds** for instant AI response (it will come from cache)\n\n⚖️ For legal visa guidance, always consult a registered migration agent.`;
        } else if (
          geminiErr?.message?.includes("authentication") ||
          geminiErr?.message?.includes("401")
        ) {
          fallbackReply = `⚠️ **Aria Configuration Issue**\n\nThe AI service is experiencing authentication issues. This is a temporary system problem.\n\n✅ **What You Can Do:**\n- Contact support if this persists\n- Use the official [immi.homeaffairs.gov.au](https://immi.homeaffairs.gov.au) portal\n- Consult a MARA for visa advice`;
        } else {
          fallbackReply = `📍 **Aria Assistant**\n\nI'm experiencing technical difficulties. Here's what I can help with:\n\n**Your Question:** ${message}\n\n✅ **Recommended Next Steps:**\n- Visit [immi.homeaffairs.gov.au](https://immi.homeaffairs.gov.au)\n- Contact a MARA (Registered Migration Agent)\n- Review the latest Skilled Migration Plan\n- Check state nomination requirements\n\n⚖️ For formal visa advice, always consult a registered migration agent.`;
        }

        res.status(200).json({ reply: fallbackReply });
      }
    } catch (err) {
      logger.error("[ariaChat] CRITICAL ERROR:", {
        message: err?.message,
        code: err?.code,
        status: err?.status,
        stack: err?.stack?.substring(0, 200),
      });
      res.status(500).json({
        error: "Aria service error. Please try again later.",
      });
    }
  }
);


exports.updateVisaFees = https.onCall({ cors: true }, async (request) => {
  const uid = requireAdmin(request);
  const payload = callablePayload(request);
  const { fees, snapshotDate } = payload;
  const db = getFirestore();
  return persistVisaFees(db, uid, fees, snapshotDate, { source: "admin_dashboard" });
});
