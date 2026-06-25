#!/usr/bin/env node

/**
 * Create Test Notification
 * Creates a draft notification in Firestore for testing the approval workflow
 */

const admin = require('firebase-admin');

async function createTestNotification() {
  try {
    // Initialize Firebase Admin SDK
    const app = admin.initializeApp({
      projectId: 'swift-shore-238707',
    });

    const db = admin.firestore(app);
    
    console.log('📝 Creating test notification draft...\n');
    
    // Generate unique ID
    const timestamp = Date.now();
    const docId = `test-e2e-${timestamp}`;
    
    const testNotification = {
      title: `Test Migration Update - VIC (${new Date().toLocaleTimeString()})`,
      body: 'New skilled migration changes for Victoria. This is a test notification.',
      category: 'update',
      url: 'https://example.com/vic-update',
      state: 'VIC',
      source: 'Test System',
      sourceUrl: 'https://example.com',
      status: 'draft',
      createdAt: admin.firestore.Timestamp.now(),
    };
    
    // Write to Firestore
    await db.collection('notifications_draft').doc(docId).set(testNotification);
    
    console.log('✅ Test notification created successfully!\n');
    console.log(`📍 Collection: notifications_draft`);
    console.log(`📍 Document ID: ${docId}`);
    console.log(`📋 Title: ${testNotification.title}`);
    console.log(`📍 State: ${testNotification.state}`);
    console.log(`📊 Status: ${testNotification.status}\n`);
    
    console.log('⏭️  Next steps:');
    console.log('1. Open admin dashboard: https://swift-shore-238707.web.app/login');
    console.log('2. Sign in with Google');
    console.log('3. Find the draft notification');
    console.log('4. Click "Approve" to test the notification workflow');
    console.log('5. Check Cloud Function logs for execution\n');
    
    console.log('📊 Firestore URL:');
    console.log('https://console.firebase.google.com/project/swift-shore-238707/firestore/data/notifications_draft\n');
    
    await app.delete();
    process.exit(0);
    
  } catch (error) {
    console.error('❌ Error:', error.message);
    process.exit(1);
  }
}

createTestNotification();
