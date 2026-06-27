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

