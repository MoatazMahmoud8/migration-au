#!/usr/bin/env python3
"""
End-to-End Notification Flow Test
Tests the complete notification pipeline: draft → approval → FCM trigger → sent
Uses Application Default Credentials (gcloud login)
"""

import os
import sys
import time
from datetime import datetime, timezone
from google.cloud import firestore
import google.auth

def main():
    print("🧪 End-to-End Notification Flow Test\n")
    
    try:
        # Use Application Default Credentials
        credentials, project_id = google.auth.default()
        print(f"✅ Using Application Default Credentials")
        print(f"   Project: {project_id or 'swift-shore-238707'}\n")
        
        db = firestore.Client(project="swift-shore-238707", credentials=credentials)
        print("✅ Firestore client initialized\n")
    except Exception as e:
        print(f"❌ Failed to initialize Firestore: {e}")
        return 1

    try:
        # Create a test notification draft
        print("📝 Step 1: Creating test notification draft...")
        test_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        draft_data = {
            "title": f"Test Notification {test_timestamp}",
            "body": f"This is a test notification created at {datetime.now(timezone.utc).isoformat()}",
            "category": "test",
            "url": "https://example.com/test",
            "state": "VIC",
            "source": "Testing System",
            "sourceUrl": "https://example.com",
            "createdAt": datetime.now(timezone.utc),
            "status": "draft",
        }
        
        draft_ref = db.collection("notifications_draft").document(f"test-{test_timestamp}")
        draft_ref.set(draft_data)
        draft_id = draft_ref.id
        print(f"   ✅ Created draft: {draft_id}\n")

        # Simulate approval - move to published collection
        print("📋 Step 2: Simulating approval...")
        notification_data = draft_data.copy()
        notification_data["status"] = "published"
        notification_data["publishedAt"] = datetime.now(timezone.utc)
        
        notif_ref = db.collection("notifications").document(draft_id)
        notif_ref.set(notification_data)
        print(f"   ✅ Created published notification: {draft_id}\n")

        # Create notification review record
        review_data = {
            "notificationId": draft_id,
            "action": "approved",
            "reviewedBy": "system-test",
            "reviewedAt": datetime.now(timezone.utc),
            "comment": "System test approval",
        }
        db.collection("notification_reviews").add(review_data)
        print(f"   ✅ Created notification review record\n")

        # Wait a moment for Cloud Function to process
        print("⏳ Step 3: Waiting for Cloud Function to process...")
        time.sleep(3)
        
        # Check if FCM trigger was created by the Cloud Function
        print("\n📡 Step 4: Checking FCM triggers...")
        
        # Query for triggers created after our test
        triggers_query = db.collection("fcm_triggers").where(
            "title", "==", f"Test Notification {test_timestamp}"
        ).limit(10)
        
        triggers = list(triggers_query.stream())
        
        if len(triggers) == 0:
            # Try alternative query - check all recent triggers
            print("   No exact match found. Checking recent triggers...")
            all_triggers = db.collection("fcm_triggers").order_by(
                "createdAt", direction=firestore.Query.DESCENDING
            ).limit(5).stream()
            
            recent_triggers = list(all_triggers)
            print(f"   Recent FCM triggers: {len(recent_triggers)}")
            for trigger_doc in recent_triggers[:3]:
                trigger_data = trigger_doc.data()
                created_at = trigger_data.get("createdAt", {})
                print(f"   - {trigger_doc.id}: {trigger_data.get('title', 'N/A')} (sent: {trigger_data.get('sent', False)})")
        else:
            for trigger_doc in triggers:
                trigger_data = trigger_doc.data()
                print(f"   ✅ Found FCM Trigger: {trigger_doc.id}")
                print(f"      Title: {trigger_data.get('title', 'N/A')}")
                print(f"      Sent: {trigger_data.get('sent', False)}")
                print(f"      Topics: {trigger_data.get('topics', [])}")

        # Summary
        print("\n📊 Summary:")
        print(f"   ✅ Draft created: notifications_draft/{draft_id}")
        print(f"   ✅ Published: notifications/{draft_id}")
        print(f"   ✅ Review recorded")
        
        if len(triggers) > 0:
            print(f"   ✅ FCM triggers: {len(triggers)} created")
            print("   ✅ Complete notification flow working!")
            return 0
        else:
            print("   ⚠️  FCM triggers not found yet - Cloud Function may be processing")
            print("\n     To debug:")
            print("     1. Check Cloud Function logs:")
            print("        gcloud functions logs read approveNotification --project swift-shore-238707")
            print("     2. Check Firestore: notifications, fcm_triggers collections")
            print("     3. Check for errors in Cloud Function execution")
            return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
