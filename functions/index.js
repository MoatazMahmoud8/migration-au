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
    const { title, body, topics, articleUrl, sent, route } = data;

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
          route: route ?? "/(tabs)/notifications",
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
 * In development (emulator), allows any authenticated user or bypasses if no auth context
 */
async function verifyAdmin(uid) {
  // Production: require valid UID
  if (!uid) {
    logger.warn(`Admin verification: No UID provided`);
    return false;
  }
  
  try {
    const user = await getAuth().getUser(uid);
    const isAdmin = user.customClaims?.admin === true;
    
    if (!isAdmin) {
      logger.warn(`Admin verification failed for ${uid}: user does not have admin claim`);
      return false;
    }
    
    logger.info(`✅ Admin verified for ${uid}`);
    return true;
  } catch (err) {
    logger.error(`Admin verification error for ${uid}:`, err);
    return false;
  }
}

/**
 * approveNotification - Move notification from draft to published and send FCM
 * 
 * Request: { notificationId, editedTitle?, editedBody? }
 * Returns: { success, message, notificationId }
 */
exports.approveNotification = https.onCall({ cors: true }, async (data, context) => {
  logger.info(`📥 [approveNotification] Called`);
  logger.info(`📥 Raw data keys: ${Object.keys(data || {}).join(', ')}`);
  
  // The httpsCallable wraps user data in a nested 'data' field
  // data structure: { rawRequest, auth, data: { userFields... }, acceptsStreaming }
  let userPayload = data?.data || data;
  
  if (userPayload && typeof userPayload === 'object') {
    const userKeys = Object.keys(userPayload);
    logger.info(`📥 User payload keys: ${userKeys.join(', ')}`);
  }
  
  // For development/emulator with live auth, context.auth might be null
  const uid = context.auth?.uid;
  if (!uid) {
    throw new https.HttpsError("unauthenticated", "User must be authenticated");
  }
  
  logger.info(`🔐 UID: ${uid}`);
  
  // Admin check - requires admin custom claim
  const isAdmin = await verifyAdmin(uid);
  if (!isAdmin) {
    throw new https.HttpsError("permission-denied", "Admin access required");
  }

  // Extract fields from userPayload
  const notificationId = userPayload?.notificationId;
  const editedTitle = userPayload?.editedTitle;
  const editedBody = userPayload?.editedBody;
  
  logger.info(`✅ Extracted: notificationId=${notificationId}`);
  
  if (!notificationId) {
    throw new https.HttpsError("invalid-argument", "notificationId is required but was not found in request data");
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
      approvedBy: uid,
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
      approver: uid,
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
exports.rejectNotification = https.onCall({ cors: true }, async (data, context) => {
  const uid = context.auth?.uid;
  if (!uid) {
    throw new https.HttpsError("unauthenticated", "User must be authenticated");
  }
  
  logger.info(`📥 rejectNotification called with uid=${uid}`);
  
  // The httpsCallable wraps user data in a nested 'data' field
  let userPayload = data?.data || data;
  
  if (userPayload && typeof userPayload === 'object') {
    const userKeys = Object.keys(userPayload);
    logger.info(`📥 User payload keys: ${userKeys.join(', ')}`);
  }
  
  // Admin check - requires admin custom claim
  const isAdmin = await verifyAdmin(uid);
  if (!isAdmin) {
    throw new https.HttpsError("permission-denied", "Admin access required");
  }

  const { notificationId, reason } = userPayload;
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
exports.editDraftNotification = https.onCall({ cors: true }, async (data, context) => {
  const uid = context.auth?.uid;
  if (!uid) {
    throw new https.HttpsError("unauthenticated", "User must be authenticated");
  }
  
  logger.info(`📥 [editDraftNotification] Called`);
  logger.info(`📥 Raw data keys: ${Object.keys(data || {}).join(', ')}`);
  
  // The httpsCallable wraps user data in a nested 'data' field
  let userPayload = data?.data || data;
  
  if (userPayload && typeof userPayload === 'object') {
    const userKeys = Object.keys(userPayload);
    logger.info(`📥 User payload keys: ${userKeys.join(', ')}`);
  }
  
  // Admin check - requires admin custom claim
  const isAdmin = await verifyAdmin(uid);
  if (!isAdmin) {
    throw new https.HttpsError("permission-denied", "Admin access required");
  }

  const { notificationId, title, body, category } = userPayload;
  logger.info(`✅ Extracted: notificationId=${notificationId}`);
  
  if (!notificationId) {
    throw new https.HttpsError("invalid-argument", "notificationId is required but was not found in request data");
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

// ─────────────────────────────────────────────────────────────────────────────
// SCRAPER UPDATE HANDLER - Auto-create notifications when scraper finds articles
// ─────────────────────────────────────────────────────────────────────────────

/**
 * onScraperUpdate - Triggers when scraper metadata updates
 * 
 * Automatically creates notifications for new migration news articles found by the scraper
 * and sends them via FCM to subscribed users.
 * 
 * Firestore Path: _scraper_meta/{state}
 * 
 * Flow:
 * 1. Detects new articles from scraper
 * 2. Creates notification in notifications collection
 * 3. Creates FCM trigger for delivery
 * 4. Sends FCM message to State topic
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

      // Extract article information
      const newArticles = data.articles || [];
      const beforeData = snap.before?.data?.() || {};
      const lastArticleCount = (beforeData.articles?.length) || 0;
      
      if (newArticles.length === lastArticleCount) {
        logger.info(
          `ℹ️ [Scraper Update] No new articles for state ${state} ` +
          `(still ${newArticles.length})`
        );
        return { status: "no_new_articles", state, count: newArticles.length };
      }

      // Get recent articles (assume scraper adds newest first)
      const newCount = Math.max(0, newArticles.length - lastArticleCount);
      let recentArticles = newArticles.slice(0, newCount);
      
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
        { state, totalNew: newCount, filteredCount: recentArticles.length }
      );

      const db = getFirestore();
      const messaging = getMessaging();
      const notifications = [];
      const errors = [];

      // Create notifications for each new article
      for (const article of recentArticles) {
        try {
          const notificationId = `scraper-${state}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
          
          // Ensure we have a valid link - use the article link or fall back to None
          const articleLink = (article.link && article.link.trim()) ? article.link.trim() : null;

          const notification = {
            title: article.title || `New ${state} Migration Update`,
            body: article.summary || article.description || "New migration news available",
            category: "migration_news",
            source: article.source || "scraper",
            sourceUrl: articleLink || "", // Will be empty if no link available
            url: articleLink || `https://swift-shore-238707.web.app/notifications`, // Fallback to Notifications page
            state: state,
            status: "published",
            articleDate: article.date || new Date().toISOString(),
            createdAt: new Date(),
            publishedAt: new Date(),
            createdBy: "scraper_automation",
            hasValidSourceUrl: !!articleLink, // Flag to indicate if link is real
          };

          // Write to notifications collection (published directly)
          await db.collection("notifications").doc(notificationId).set(notification);
          logger.info(
            `✅ [Scraper Update] Created notification: ${notificationId}`,
            { title: notification.title }
          );

          // Create FCM trigger document
          const fcmTriggerId = `fcm-${notificationId}`;
          const topics = [
            `state_${state}`,
            "au_migration",
          ];

          await db.collection("fcm_triggers").doc(fcmTriggerId).set({
            notificationId,
            title: notification.title,
            body: notification.body,
            topics,
            url: notification.url,
            route: "/(tabs)/notifications",
            sent: false,
            sentAt: null,
            createdAt: new Date(),
            error: null,
          });

          logger.info(
            `📨 [Scraper Update] Created FCM trigger for topics: ${topics.join(", ")}`,
            { fcmTriggerId }
          );

          notifications.push({
            notificationId,
            fcmTriggerId,
            title: notification.title,
          });

        } catch (articleError) {
          logger.error(
            `❌ [Scraper Update] Error processing article for ${state}`,
            { error: articleError }
          );
          errors.push(articleError.message);
        }
      }

      // Send FCM messages for each notification
      for (const notif of notifications) {
        try {
          const response = await messaging.send({
            notification: {
              title: notif.title,
              body: "📰 New migration update available",
            },
            data: {
              route: "/(tabs)/notifications",
              notificationId: notif.notificationId,
              url: "app://notifications",
            },
            topic: `state_${state}`,
          });

          // Mark FCM trigger as sent
          await db.collection("fcm_triggers").doc(notif.fcmTriggerId).update({
            sent: true,
            sentAt: new Date(),
            route: "/(tabs)/notifications",
          });

          logger.info(
            `✅ [Scraper Update] FCM sent to state_${state}`,
            { messageId: response, notificationId: notif.notificationId }
          );

        } catch (fcmError) {
          logger.error(
            `❌ [Scraper Update] FCM send failed for ${notif.notificationId}`,
            { error: fcmError }
          );

          // Log error to FCM trigger
          await db.collection("fcm_triggers").doc(notif.fcmTriggerId).update({
            sent: false,
            error: fcmError.message,
            sentAt: new Date(),
          });
          
          errors.push(fcmError.message);
        }
      }

      logger.info(
        `🎉 [Scraper Update] Complete for ${state}`,
        { 
          state,
          notificationsCreated: notifications.length,
          errors: errors.length > 0 ? errors : null,
          timestamp: new Date().toISOString(),
        }
      );

      return {
        status: "success",
        state,
        notificationsCreated: notifications.length,
        notifications,
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

