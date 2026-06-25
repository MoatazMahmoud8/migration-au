# End-to-End Notification System Test Guide

**Objective**: Test the complete notification delivery pipeline from draft → approval → FCM → mobile app

## System Architecture

```
Admin Dashboard
    ↓ (User approves notification)
Firestore: notifications collection
    ↓ (Cloud Function trigger)
approveNotification() Cloud Function
    ↓ (Creates trigger document)
Firestore: fcm_triggers collection
    ↓ (Cloud Function trigger)
processFcmTrigger() Cloud Function
    ↓ (Sends FCM message)
Firebase Cloud Messaging (FCM)
    ↓ (Routes to subscribed clients)
Mobile App (Expo)
    ↓ (Receives and displays)
User Notification
```

## Phase 1: Prepare Test Data

### Step 1.1: Create Test Notification Draft

Option A: Via Admin Dashboard
1. Open https://swift-shore-238707.web.app/login
2. Sign in with Google (admin account required)
3. Navigate to dashboard
4. Create a new notification draft
5. Title: `E2E Test Notification - $(date +%s)`
6. Body: `Testing end-to-end notification flow`
7. State: `VIC`
8. Save as draft

Option B: Via Firebase Console
1. Go to Firebase Console → Firestore
2. Collection: `notifications_draft`
3. Add document with:
   ```json
   {
     "title": "E2E Test Notification - 1717946400000",
     "body": "Testing end-to-end notification flow",
     "category": "test",
     "url": "https://example.com/test",
     "state": "VIC",
     "source": "Test System",
     "sourceUrl": "https://example.com",
     "createdAt": "2026-06-09T14:00:00Z",
     "status": "draft"
   }
   ```

### Step 1.2: Verify Draft Created

```bash
# Check notifications_draft collection
firebase firestore:collection notifications_draft --project swift-shore-238707
# Or via console at: https://console.firebase.google.com/project/swift-shore-238707/firestore/data/notifications_draft
```

Expected: See your draft notification in the list

## Phase 2: Test Approval Workflow

### Step 2.1: Approve Notification

Option A: Via Admin Dashboard
1. Open https://swift-shore-238707.web.app/admin/dashboard
2. Find your test notification
3. Click "Approve"
4. Confirm approval

Option B: Via Cloud Function (Direct)
```bash
# Approve via HTTP trigger
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"notificationId": "test-1717946400000"}' \
  https://us-central1-swift-shore-238707.cloudfunctions.net/approveNotification

# Expected response: {"status": "success", "message": "Notification approved"}
```

### Step 2.2: Verify Notification Published

Expected: Notification moves to `notifications` collection

```bash
# Check notifications collection
firebase firestore:collection notifications --project swift-shore-238707
# Should show your approved notification with status "published"
```

## Phase 3: Verify Cloud Function Processing

### Step 3.1: Wait for FCM Trigger Creation

The `approveNotification` Cloud Function should:
1. Read approved notification
2. Create document in `fcm_triggers` collection
3. Log: `Created FCM trigger for notification {id}`

```bash
# Monitor Cloud Function logs in real-time
gcloud functions logs read approveNotification \
  --project swift-shore-238707 \
  --limit 50 \
  --follow

# Or check batch:
gcloud functions logs read approveNotification \
  --project swift-shore-238707 \
  --limit 20
```

### Step 3.2: Verify FCM Trigger Created

Expected: Document appears in `fcm_triggers` collection

```bash
# Check fcm_triggers collection
firebase firestore:collection fcm_triggers --project swift-shore-238707

# Should show document with:
# - title: Notification title
# - body: Notification body
# - topics: ["State_VIC"] (and any occupation codes)
# - sent: false
```

## Phase 4: Verify FCM Processing

### Step 4.1: Monitor processFcmTrigger Function

The `processFcmTrigger` Cloud Function should:
1. Read FCM trigger document
2. Send FCM message to topics
3. Update trigger document: `sent: true`
4. Log: `Sent FCM message to topics: [...]`

```bash
# Monitor processFcmTrigger logs
gcloud functions logs read processFcmTrigger \
  --project swift-shore-238707 \
  --limit 50 \
  --follow

# Or batch:
gcloud logging read \
  "resource.type=cloud_function AND resource.labels.function_name=processFcmTrigger" \
  --project swift-shore-238707 \
  --limit 30 \
  --format="table(timestamp, severity, textPayload)"
```

### Step 4.2: Verify Trigger Marked as Sent

Expected: `fcm_triggers` document updated with `sent: true`

```bash
# Check specific trigger
firebase firestore:document fcm_triggers/{trigger-id} --project swift-shore-238707
# Should show: "sent": true, "sentAt": "2026-06-09T14:05:00Z"
```

## Phase 5: Verify Mobile App Receives Notification

### Step 5.1: Ensure Mobile App Subscribed to Topics

Check mobile app initialization logs:

```bash
# Mobile app logs should show:
# "[_layout] ✅ Notifications initialized successfully"
# "[_layout] Subscribing to global topics..."
# "[_layout] ✅ State topic subscribed: state_VIC"
```

### Step 5.2: Check FCM Message Receipt

In mobile app logs, expect:

```
[FCM] Message received from topic: State_VIC
[FCM] Title: "E2E Test Notification - 1717946400000"
[FCM] Body: "Testing end-to-end notification flow"
[Notification] Displaying local notification
```

### Step 5.3: Verify Local Notification Display

On device/simulator:
1. Look for system notification: "E2E Test Notification - 1717946400000"
2. Notification body: "Testing end-to-end notification flow"
3. Tap to open - should navigate to https://example.com/test

## Troubleshooting Guide

### Issue: Draft Not Created
```bash
# Verify Firestore connectivity
firebase firestore:list-documents notifications_draft --project swift-shore-238707
# If fails: Check authentication, project ID, Firestore enabled
```

### Issue: Approval Fails
```bash
# Check Cloud Function for errors
gcloud functions logs read approveNotification --project swift-shore-238707 --limit 10
# Common issues: auth token expired, invalid notification ID, permission denied
```

### Issue: FCM Trigger Not Created
```bash
# Check approveNotification function logs for:
# - "Creating FCM trigger..."
# - Any error messages
# Possible causes:
#   - Function timed out
#   - Firestore write permission denied
#   - Invalid topic names
```

### Issue: Notification Not Received on Mobile
```bash
# Check mobile app logs for:
# - FCM token obtained successfully
# - Topic subscription successful
# - Permission granted
# - Foreground notification handler registered

# If using TestFlight:
# - Check TestFlight notification permissions
# - Verify app not in "Do Not Disturb"
# - Check Firestore security rules allow topic subscriptions
```

### Issue: FCM Marked as Sent but No Message Received
```bash
# Possible causes:
#   1. Topic name mismatch (e.g., "State_VIC" vs "state_vic")
#   2. Mobile app not subscribed to correct topic
#   3. FCM message rejected by provider
#   4. Mobile app in background with message not configured correctly
#   5. Notification permission denied on device

# Verify topic subscriptions in Firestore:
firebase firestore:document mobile_subscriptions/{userId} --project swift-shore-238707
```

## Success Criteria

✅ All tests pass when:
1. Draft notification created in `notifications_draft`
2. Approval moves notification to `notifications` with `status: published`
3. FCM trigger created in `fcm_triggers` with correct topics
4. Cloud Function logs show successful FCM send
5. FCM trigger marked as `sent: true` with `sentAt` timestamp
6. Mobile app receives notification
7. Notification displays on device

## Automated Verification

Run the complete test suite:

```bash
cd /path/to/migration-au/repo
python3 test-notification-flow.py
```

This script will:
1. Create test draft
2. Simulate approval
3. Wait for Cloud Function processing
4. Verify FCM trigger created
5. Check trigger sent status
6. Report overall system health
