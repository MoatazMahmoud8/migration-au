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
const { getMessaging } = require("firebase-admin/messaging");
const { getFirestore } = require("firebase-admin/firestore");
const { initializeApp } = require("firebase-admin/app");
const { logger } = require("firebase-functions");

initializeApp();

/**
 * Triggered whenever a new document lands in `fcm_triggers`.
 * Sends one FCM multicast per topic listed in the document,
 * then marks the trigger document as sent.
 */
exports.processFcmTrigger = onDocumentCreated(
  "fcm_triggers/{triggerId}",
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
