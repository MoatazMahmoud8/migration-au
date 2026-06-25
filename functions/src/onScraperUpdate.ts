import * as functions from "firebase-functions";
import * as admin from "firebase-admin";

admin.initializeApp();
const db = admin.firestore();
const messaging = admin.messaging();

/**
 * Cloud Function: onScraperUpdate
 * 
 * Triggers when scraper metadata updates and automatically creates notifications
 * for new migration news articles, then sends them via FCM to subscribed users.
 * 
 * Firestore Path: _scraper_meta/{state}
 * 
 * When triggered:
 * 1. Detects new articles from scraper
 * 2. Creates notification in notifications_draft
 * 3. Auto-publishes notification
 * 4. Creates FCM trigger for FCM delivery
 * 5. Tracks notification as sent
 */
export const onScraperUpdate = functions.firestore
  .document("_scraper_meta/{state}")
  .onWrite(async (change, context) => {
    const state = context.params.state;
    
    try {
      functions.logger.info(`📡 [Scraper Update] Detected update for state: ${state}`, {
        state,
        timestamp: new Date().toISOString(),
      });

      // Get the new data from scraper
      const data = change.after.data();
      if (!data) {
        functions.logger.warn(`⚠️ [Scraper Update] No data for state: ${state}`);
        return { status: "no_data", state };
      }

      // Extract article information
      const newArticles = data.articles || [];
      const lastArticleCount = (change.before.data()?.articles?.length) || 0;
      
      if (newArticles.length === lastArticleCount) {
        functions.logger.info(
          `ℹ️ [Scraper Update] No new articles for state ${state} ` +
          `(still ${newArticles.length})`
        );
        return { status: "no_new_articles", state, count: newArticles.length };
      }

      // Get recent articles (assume scraper adds newest first)
      const recentArticles = newArticles.slice(0, Math.max(0, newArticles.length - lastArticleCount));
      
      functions.logger.info(
        `🔍 [Scraper Update] Found ${recentArticles.length} new articles for ${state}`,
        { state, newCount: newArticles.length, previousCount: lastArticleCount }
      );

      const notifications: any[] = [];

      // Create notifications for each new article
      for (const article of recentArticles) {
        try {
          const notificationId = `scraper-${state}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
          
          const notification = {
            title: article.title || `New ${state} Migration Update`,
            body: article.summary || article.description || "New migration news available",
            category: "migration_news",
            source: "scraper",
            sourceUrl: article.link || "",
            url: article.link || "https://swift-shore-238707.web.app/notifications",
            state: state,
            status: "published",
            articleDate: article.date || new Date().toISOString(),
            createdAt: new Date(),
            publishedAt: new Date(),
            createdBy: "scraper_automation",
          };

          // Write to notifications collection (published directly)
          await db.collection("notifications").doc(notificationId).set(notification);
          functions.logger.info(
            `✅ [Scraper Update] Created notification: ${notificationId}`,
            { title: notification.title }
          );

          // Create FCM trigger document
          const fcmTriggerId = `fcm-${notificationId}`;
          const topics = [
            `State_${state}`,
            "au_migration",
          ];

          await db.collection("fcm_triggers").doc(fcmTriggerId).set({
            notificationId,
            title: notification.title,
            body: notification.body,
            topics,
            url: notification.url,
            sent: false,
            sentAt: null,
            createdAt: new Date(),
            error: null,
          });

          functions.logger.info(
            `📨 [Scraper Update] Created FCM trigger for topics: ${topics.join(", ")}`,
            { fcmTriggerId }
          );

          notifications.push({
            notificationId,
            fcmTriggerId,
            title: notification.title,
          });

        } catch (articleError) {
          functions.logger.error(
            `❌ [Scraper Update] Error processing article for ${state}`,
            { error: articleError }
          );
        }
      }

      // Send FCM messages for each notification
      for (const notif of notifications) {
        try {
          const response = await messaging.send({
            notification: {
              title: notif.title,
              body: `📰 New migration update available`,
            },
            data: {
              notificationId: notif.notificationId,
              url: "app://notifications",
            },
            topic: `State_${state}`,
          });

          // Mark FCM trigger as sent
          await db.collection("fcm_triggers").doc(notif.fcmTriggerId).update({
            sent: true,
            sentAt: new Date(),
          });

          functions.logger.info(
            `✅ [Scraper Update] FCM sent to State_${state}`,
            { messageId: response, notificationId: notif.notificationId }
          );

        } catch (fcmError) {
          functions.logger.error(
            `❌ [Scraper Update] FCM send failed for ${notif.notificationId}`,
            { error: fcmError }
          );

          // Log error to FCM trigger
          await db.collection("fcm_triggers").doc(notif.fcmTriggerId).update({
            sent: false,
            error: (fcmError as Error).message,
            sentAt: new Date(),
          });
        }
      }

      functions.logger.info(
        `🎉 [Scraper Update] Complete for ${state}`,
        { 
          state,
          notificationsCreated: notifications.length,
          timestamp: new Date().toISOString(),
        }
      );

      return {
        status: "success",
        state,
        notificationsCreated: notifications.length,
        notifications,
      };

    } catch (error) {
      functions.logger.error(
        `❌ [Scraper Update] Fatal error for state ${state}`,
        { error, state }
      );
      
      return {
        status: "error",
        state,
        error: (error as Error).message,
      };
    }
  });
