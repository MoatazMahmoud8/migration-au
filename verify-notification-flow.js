#!/usr/bin/env node

/**
 * Verify Notification Flow
 * This script checks if the scraper created notifications and if FCM triggers were created
 */

const admin = require('firebase-admin');
const path = require('path');

// Initialize Firebase Admin
const serviceAccountPath = process.env.GOOGLE_APPLICATION_CREDENTIALS || 
  path.join(process.env.HOME, '.config/gcloud/application_default_credentials.json');

const app = admin.initializeApp({
  projectId: 'swift-shore-238707',
});

const db = admin.firestore(app);
const messaging = admin.messaging(app);

async function main() {
  try {
    console.log('🔍 Checking notification collections...\n');

    // Check notifications_draft collection
    console.log('📋 notifications_draft collection:');
    const drafts = await db.collection('notifications_draft').limit(5).get();
    console.log(`   Count: ${drafts.size} documents`);
    if (drafts.size > 0) {
      console.log('   Recent drafts:');
      drafts.docs.forEach(doc => {
        const data = doc.data();
        console.log(`   - ${doc.id}: "${data.title}" (${data.status || 'unknown'})`);
      });
    } else {
      console.log('   ⚠️  No draft notifications found');
    }
    console.log();

    // Check notifications collection
    console.log('📋 notifications collection:');
    const notifications = await db.collection('notifications').limit(5).get();
    console.log(`   Count: ${notifications.size} documents`);
    if (notifications.size > 0) {
      console.log('   Recent notifications:');
      notifications.docs.forEach(doc => {
        const data = doc.data();
        console.log(`   - ${doc.id}: "${data.title}" (${new Date(data.createdAt?.toDate?.() || data.createdAt).toLocaleString()})`);
      });
    } else {
      console.log('   ⚠️  No notifications found');
    }
    console.log();

    // Check fcm_triggers collection
    console.log('📋 fcm_triggers collection:');
    const triggers = await db.collection('fcm_triggers').limit(5).get();
    console.log(`   Count: ${triggers.size} documents`);
    if (triggers.size > 0) {
      console.log('   Recent triggers:');
      triggers.docs.forEach(doc => {
        const data = doc.data();
        console.log(`   - ${doc.id}: "${data.title}" (sent: ${data.sent ? '✅' : '⏳'})`);
        if (data.topics) {
          console.log(`     Topics: ${data.topics.join(', ')}`);
        }
      });
    } else {
      console.log('   ⚠️  No FCM triggers found');
    }
    console.log();

    // Check notification_reviews collection
    console.log('📋 notification_reviews collection:');
    const reviews = await db.collection('notification_reviews').limit(5).get();
    console.log(`   Count: ${reviews.size} documents`);
    if (reviews.size > 0) {
      console.log('   Recent reviews:');
      reviews.docs.forEach(doc => {
        const data = doc.data();
        console.log(`   - ${doc.id}: ${data.action} by ${data.reviewedBy}`);
      });
    } else {
      console.log('   ⚠️  No reviews found');
    }
    console.log();

    // Summary
    console.log('📊 Summary:');
    console.log(`   Drafts: ${drafts.size}`);
    console.log(`   Published: ${notifications.size}`);
    console.log(`   FCM Triggers: ${triggers.size}`);
    console.log(`   Reviews: ${reviews.size}`);
    console.log();

    if (triggers.size === 0 && notifications.size === 0) {
      console.log('🔴 No notifications have been created yet');
      console.log('   This could mean:');
      console.log('   1. Scraper workflow failed to create notifications');
      console.log('   2. No approvals were made on draft notifications');
      console.log('   3. Cloud Function has not processed approvals yet');
    } else if (triggers.size === 0 && notifications.size > 0) {
      console.log('🟡 Notifications created but FCM triggers not sent');
      console.log('   Possible causes:');
      console.log('   1. approveNotification Cloud Function failed');
      console.log('   2. FCM topic subscription limits reached');
    } else {
      console.log('✅ Notifications and FCM triggers successfully created');
    }

  } catch (error) {
    console.error('❌ Error:', error.message);
    process.exit(1);
  } finally {
    await app.delete();
  }
}

main();
