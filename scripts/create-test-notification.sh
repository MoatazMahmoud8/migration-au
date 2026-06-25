#!/bin/bash
# Test Notification Creation Script
# This script creates a test draft notification in Firestore
# which can then be manually approved to test the FCM flow

PROJECT_ID="swift-shore-238707"
FIRESTORE_JSON="/tmp/test-notification.json"

# Create a test notification draft
cat > "$FIRESTORE_JSON" << 'EOF'
{
  "title": "Test Notification - $(date +%s)",
  "body": "This is a test notification from the CLI",
  "category": "test",
  "url": "https://example.com/test",
  "state": "VIC",
  "source": "Testing System",
  "sourceUrl": "https://example.com",
  "createdAt": "2026-06-09T21:30:00Z",
  "status": "draft"
}
EOF

echo "📝 Creating test notification draft in Firestore..."
firebase firestore:set "notifications_draft/test-notification-cli-$(date +%s)" "$FIRESTORE_JSON" \
  --project "$PROJECT_ID" \
  --merge 2>&1

if [ $? -eq 0 ]; then
  echo "✅ Test notification created successfully"
  echo "📍 Collection: notifications_draft"
  echo "📍 Document: test-notification-cli-$(date +%s)"
  echo ""
  echo "Next steps:"
  echo "1. Sign in to admin dashboard: https://swift-shore-238707.web.app"
  echo "2. Click 'Approve' on the test notification"
  echo "3. Check Firebase Hosting for fcm_triggers collection"
  echo "4. Check Cloud Function logs: firebase functions:log --project $PROJECT_ID"
else
  echo "❌ Failed to create test notification"
  exit 1
fi
