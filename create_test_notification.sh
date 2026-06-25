#!/bin/bash

PROJECT_ID="swift-shore-238707"
TIMESTAMP=$(date +%s)
DOC_ID="test-e2e-${TIMESTAMP}"

echo "📝 Phase 1: Creating test notification draft..."
echo ""

# Create a temporary JSON file
cat > /tmp/notification.json << 'JSON'
{
  "fields": {
    "title": {
      "stringValue": "E2E Test: VIC Update"
    },
    "body": {
      "stringValue": "Testing complete notification workflow: draft → approval → FCM → mobile"
    },
    "category": {
      "stringValue": "test"
    },
    "url": {
      "stringValue": "https://example.com/test-e2e"
    },
    "state": {
      "stringValue": "VIC"
    },
    "source": {
      "stringValue": "E2E Test System"
    },
    "sourceUrl": {
      "stringValue": "https://example.com"
    },
    "status": {
      "stringValue": "draft"
    },
    "createdAt": {
      "timestampValue": "2026-06-09T22:00:00Z"
    }
  }
}
JSON

# Try using curl with REST API
ACCESS_TOKEN=$(gcloud auth application-default print-access-token 2>/dev/null || gcloud auth print-access-token 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ]; then
  echo "⚠️  Could not get authentication token"
  echo ""
  echo "✅ Alternative: Create manually via Firebase Console"
  echo ""
  echo "Steps:"
  echo "1. Open: https://console.firebase.google.com/project/$PROJECT_ID/firestore"
  echo "2. Click 'notifications_draft' collection"
  echo "3. Click '+ Add Document'"
  echo "4. Enter Document ID: $DOC_ID"
  echo "5. Add this data:"
  cat /tmp/notification.json
  exit 1
fi

echo "✅ Got authentication token"
echo ""

# Use REST API to create document
echo "Sending to Firestore REST API..."
curl -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/notification.json \
  "https://firestore.googleapis.com/v1/projects/$PROJECT_ID/databases/(default)/documents/notifications_draft?documentId=$DOC_ID" \
  2>/dev/null

echo ""
echo "✅ Test notification should be created!"
echo "Document ID: $DOC_ID"

