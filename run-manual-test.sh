#!/bin/bash

# Complete Manual E2E Notification Test Procedure
# Since automated testing requires admin dashboard access, here's the manual procedure

PROJECT_ID="swift-shore-238707"

cat << 'EOF'

🧪 COMPLETE END-TO-END NOTIFICATION TEST
==========================================

This guide walks you through manually testing the notification system from draft to FCM delivery.

## 📋 PREREQUISITES
- Google account with admin access to swift-shore-238707
- Expo mobile app installed on device/simulator
- Browser with Firebase Console access

## 🎬 TEST PROCEDURE

### PHASE 1: CREATE TEST NOTIFICATION DRAFT (5 min)

1. Open Firebase Console:
   https://console.firebase.google.com/project/swift-shore-238707/firestore

2. Select "notifications_draft" collection

3. Click "+ Add Document"

4. Enter Document ID: test-e2e-$(date +%s%N | cut -b1-13)

5. Copy and paste this data (click "Edit" after creating):

EOF

cat << 'JSON'
{
  "title": "Test E2E Notification - VIC",
  "body": "Testing the complete notification workflow: draft → approval → FCM → mobile app",
  "category": "test",
  "url": "https://example.com/test-e2e",
  "state": "VIC",
  "source": "E2E Test System",
  "sourceUrl": "https://example.com",
  "status": "draft",
  "createdAt": "2026-06-09T14:00:00Z",
  "occupations": ["261311"]
}
JSON

cat << 'EOF'

6. Click "Save"

✅ Draft notification created successfully!

---

### PHASE 2: APPROVE NOTIFICATION (3 min)

Option A: VIA ADMIN DASHBOARD (Recommended)
1. Open: https://swift-shore-238707.web.app/login
2. Sign in with Google (must be admin account)
3. Navigate to Notifications page
4. Find your test notification
5. Click "Approve"
6. Confirm in dialog

Option B: VIA FIREBASE CONSOLE (If dashboard unavailable)
1. In Firestore Console, select "notifications" collection
2. Manually create a document with the same ID as your draft
3. Copy data from draft
4. Change status: "draft" → "published"
5. Add field: publishedAt: "2026-06-09T14:05:00Z"
6. Click "Save"

✅ Notification published!

---

### PHASE 3: VERIFY FCM TRIGGER CREATED (2 min)

1. Go to Firestore Console
2. Select "fcm_triggers" collection
3. Look for a document created in the last 2 minutes
4. Check it contains:
   ✓ "title": "Test E2E Notification - VIC"
   ✓ "sent": false or true
   ✓ "topics": ["State_VIC", ...occupations...]
   ✓ "createdAt": Recent timestamp

If NOT FOUND after 30 seconds:
  → Check approveNotification Cloud Function logs (see TROUBLESHOOTING)

✅ FCM trigger verified!

---

### PHASE 4: CHECK CLOUD FUNCTION EXECUTION (3 min)

1. Cloud Functions console:
   https://console.cloud.google.com/functions/details/us-central1/approveNotification?project=swift-shore-238707

2. Click "LOGS" tab

3. Look for execution with timestamp matching your approval

4. Verify logs show:
   ✓ "Notification received"
   ✓ "Creating FCM trigger"
   ✓ "FCM trigger created successfully"

5. Check processFcmTrigger function:
   https://console.cloud.google.com/functions/details/us-central1/processFcmTrigger?project=swift-shore-238707

6. Verify logs show:
   ✓ "FCM trigger received"
   ✓ "Sending FCM message"
   ✓ "FCM message sent successfully"

✅ Cloud Functions executing correctly!

---

### PHASE 5: VERIFY MOBILE APP RECEIVES NOTIFICATION (2 min)

1. Open Expo TestFlight app on device/simulator
2. Check system notification center
3. Look for:
   - Title: "Test E2E Notification - VIC"
   - Body: "Testing the complete notification workflow..."

4. Tap notification to open
5. Verify it opens to https://example.com/test-e2e

If NOT RECEIVED after 1 minute:
  → Check mobile app logs (see TROUBLESHOOTING)

✅ Notification delivery complete!

---

## 📊 SUCCESS CRITERIA

All tests pass when:
✅ Draft notification created in notifications_draft
✅ Notification moved to notifications collection after approval
✅ FCM trigger document created in fcm_triggers collection
✅ Cloud Functions show successful execution logs
✅ Mobile app receives notification
✅ Notification displays with correct content
✅ Tapping notification opens correct URL

## 🔧 MONITORING LOGS IN REAL-TIME

While running the test, open a terminal and monitor logs:

# Monitor approveNotification function
gcloud functions logs read approveNotification \
  --project swift-shore-238707 \
  --limit 10 \
  --follow

# Monitor processFcmTrigger function
gcloud functions logs read processFcmTrigger \
  --project swift-shore-238707 \
  --limit 10 \
  --follow

# Monitor all Cloud Functions
gcloud logging read "resource.type=cloud_function" \
  --project swift-shore-238707 \
  --limit 20 \
  --follow

## 🐛 TROUBLESHOOTING

### Issue: Draft not created
- Check Firebase project is swift-shore-238707
- Verify you have write access to Firestore
- Try creating a different collection document to verify connection

### Issue: Approval fails
- Check admin dashboard console for errors (F12)
- Verify user has admin Firebase claim set
- Try approving via Firebase Console instead

### Issue: FCM trigger not created
- Check approveNotification Cloud Function logs
- Look for errors: "permission denied", "firestore error"
- Verify fcm_triggers collection exists
- Check Cloud Function execution time (should be <5 seconds)

### Issue: Notification not received on mobile
- Check mobile app has FCM permission granted
- Verify app is subscribed to topics (check app logs)
- Check notification permission in device settings
- Verify test topic matches subscription (e.g., "State_VIC")
- Try closing and reopening app

### Issue: Getting logs
Run directly:
gcloud functions logs read <FUNCTION_NAME> \
  --project swift-shore-238707 \
  --limit 50 2>&1 | tail -30

## 📈 EXPECTED TIMINGS

- Draft creation: Instant
- Approval to notification published: <1 second
- Publishing to FCM trigger created: <5 seconds
- FCM trigger to mobile receipt: <10 seconds
- Total end-to-end: <20 seconds

If any step takes longer than 2x expected, check logs for errors.

## 🔗 USEFUL LINKS

Firestore: https://console.firebase.google.com/project/swift-shore-238707/firestore
Cloud Functions: https://console.cloud.google.com/functions?project=swift-shore-238707
Cloud Logs: https://console.cloud.google.com/logs?project=swift-shore-238707
Admin Dashboard: https://swift-shore-238707.web.app
Mobile App: [Your TestFlight link]

## ✅ WHEN TEST IS COMPLETE

Document the results:
1. Timestampt all steps completed
2. Screenshot of Firebase Hosting health check
3. Screenshot of FCM trigger in Firestore
4. Screenshot of notification on mobile device

Share results to confirm system is working end-to-end!

EOF

cat << EOF

Generated: $(date)
Project: swift-shore-238707
Document: E2E_NOTIFICATION_TEST_MANUAL.md

EOF
