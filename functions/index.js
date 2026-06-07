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
const { getAuth } = require("firebase-admin/auth");
const { initializeApp } = require("firebase-admin/app");
const { logger } = require("firebase-functions");

initializeApp();

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
    const { title, body, topics, articleUrl, sent } = data;

    // Guard — skip if already processed (e.g. function retry)
    if (sent === true) {
      logger.info(`Trigger ${event.params.triggerId} already sent — skipping`);
      return;
    }

    if (!topics || topics.length === 0) {
      logger.warn("No topics in trigger document — skipping FCM send");
      await snap.ref.update({ sent: true, skippedReason: "no_topics" });
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
          url: articleUrl ?? "",
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

/**
 * Verify admin role from custom claims
 */
async function verifyAdmin(uid) {
  try {
    const user = await getAuth().getUser(uid);
    return user.customClaims?.admin === true;
  } catch (err) {
    logger.warn(`Admin verification failed for ${uid}:`, err);
    return false;
  }
}

/**
 * approveNotification - Move notification from draft to published and send FCM
 * 
 * Request: { notificationId, editedTitle?, editedBody? }
 * Returns: { success, message, notificationId }
 */
exports.approveNotification = https.onCall(async (data, context) => {
  // Auth check
  if (!context.auth) {
    throw new https.HttpsError(
      "unauthenticated",
      "User must be authenticated"
    );
  }

  // Admin check
  const isAdmin = await verifyAdmin(context.auth.uid);
  if (!isAdmin) {
    throw new https.HttpsError("permission-denied", "Admin access required");
  }

  const { notificationId, editedTitle, editedBody } = data;
  if (!notificationId) {
    throw new https.HttpsError("invalid-argument", "notificationId required");
  }

  const db = getFirestore();

  try {
    // Get draft notification
    const draftRef = db.collection("notifications_draft").doc(notificationId);
    const draftSnap = await draftRef.get();

    if (!draftSnap.exists) {
      throw new https.HttpsError("not-found", "Draft notification not found");
    }

    const draftData = draftSnap.data();

    // Build published notification (with optional edits)
    const publishedData = {
      ...draftData,
      title: editedTitle || draftData.title,
      body: editedBody || draftData.body,
      status: "published",
      approvedAt: new Date().toISOString(),
      approvedBy: context.auth.uid,
    };

    // Save to published collection
    await db.collection("notifications").doc(notificationId).set(publishedData);

    // Create FCM trigger for this notification
    if (publishedData.url) {
      const triggerId = notificationId.substring(0, 12);
      const topics = ["au_migration"];

      if (publishedData.state && publishedData.state !== "FED") {
        topics.push(`state_${publishedData.state}`);
      }

      const trigger = {
        title: publishedData.title,
        body: publishedData.body,
        topics,
        articleUrl: publishedData.url,
        createdAt: new Date(),
        sent: false,
      };

      await db.collection("fcm_triggers").doc(triggerId).set(trigger);
    }

    // Record in audit trail
    await db.collection("notification_reviews").add({
      notificationId,
      action: "approved",
      approver: context.auth.uid,
      timestamp: new Date().toISOString(),
      editedTitle: editedTitle || null,
      editedBody: editedBody || null,
    });

    // Delete from draft
    await draftRef.delete();

    logger.info(`✓ Approved notification: ${notificationId}`);

    return {
      success: true,
      message: "Notification published successfully",
      notificationId,
    };
  } catch (err) {
    logger.error(`Error approving notification ${notificationId}:`, err);
    throw new https.HttpsError("internal", err.message || "Approval failed");
  }
});

/**
 * rejectNotification - Delete from draft and log rejection
 * 
 * Request: { notificationId, reason }
 * Returns: { success, message }
 */
exports.rejectNotification = https.onCall(async (data, context) => {
  if (!context.auth) {
    throw new https.HttpsError(
      "unauthenticated",
      "User must be authenticated"
    );
  }

  const isAdmin = await verifyAdmin(context.auth.uid);
  if (!isAdmin) {
    throw new https.HttpsError("permission-denied", "Admin access required");
  }

  const { notificationId, reason } = data;
  if (!notificationId) {
    throw new https.HttpsError("invalid-argument", "notificationId required");
  }

  const db = getFirestore();

  try {
    const draftRef = db.collection("notifications_draft").doc(notificationId);
    const draftSnap = await draftRef.get();

    if (!draftSnap.exists) {
      throw new https.HttpsError("not-found", "Draft notification not found");
    }

    // Record rejection in audit trail
    await db.collection("notification_reviews").add({
      notificationId,
      action: "rejected",
      rejector: context.auth.uid,
      timestamp: new Date().toISOString(),
      rejectionReason: reason || "No reason provided",
    });

    // Delete from draft
    await draftRef.delete();

    logger.info(`✓ Rejected notification: ${notificationId} | Reason: ${reason}`);

    return {
      success: true,
      message: "Notification rejected and removed from draft",
      notificationId,
    };
  } catch (err) {
    logger.error(`Error rejecting notification ${notificationId}:`, err);
    throw new https.HttpsError("internal", err.message || "Rejection failed");
  }
});

/**
 * editDraftNotification - Edit a draft notification before approval
 * 
 * Request: { notificationId, title?, body?, category? }
 * Returns: { success, message, notification }
 */
exports.editDraftNotification = https.onCall(async (data, context) => {
  if (!context.auth) {
    throw new https.HttpsError(
      "unauthenticated",
      "User must be authenticated"
    );
  }

  const isAdmin = await verifyAdmin(context.auth.uid);
  if (!isAdmin) {
    throw new https.HttpsError("permission-denied", "Admin access required");
  }

  const { notificationId, title, body, category } = data;
  if (!notificationId) {
    throw new https.HttpsError("invalid-argument", "notificationId required");
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
      updatedBy: context.auth.uid,
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
    throw new https.HttpsError("internal", err.message || "Edit failed");
  }
});

