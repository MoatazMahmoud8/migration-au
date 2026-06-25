#!/usr/bin/env python3
"""
Add test notification draft to Firestore Emulator
Usage: FIRESTORE_EMULATOR_HOST=localhost:8080 python3 add_test_draft.py
"""

import os
import json
from datetime import datetime
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Check if using emulator
emulator_host = os.getenv('FIRESTORE_EMULATOR_HOST')
if emulator_host:
    print(f"🔥 Using Firestore Emulator at {emulator_host}")
else:
    print("⚠️  FIRESTORE_EMULATOR_HOST not set - using production database!")

# Initialize Firebase Admin SDK
try:
    # Try to load service account key
    cred_path = os.path.join(os.path.dirname(__file__), '..', 'serviceAccountKey.json')
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {'projectId': 'swift-shore-238707'})
    else:
        # Use default credentials
        firebase_admin.initialize_app(options={'projectId': 'swift-shore-238707'})
except Exception as e:
    print(f"⚠️  Error loading credentials: {e}")
    # Continue anyway - might work with FIRESTORE_EMULATOR_HOST

db = firestore.client()

def add_test_draft():
    """Add a test notification draft to the emulator"""
    timestamp = datetime.now()
    
    test_draft = {
        'title': 'Test: NSW Migration Policy Update',
        'body': 'This is a test notification to verify the admin dashboard is connected to the local Firestore emulator.',
        'source': 'test_script',
        'state': 'NSW',
        'category': 'migration-policy',
        'url': 'https://example.com/test',
        'priority': 'normal',
        'createdAt': timestamp,
        'updatedAt': timestamp,
        'metadata': {
            'testData': True,
            'addedVia': 'add_test_draft.py',
            'timestamp': timestamp.isoformat()
        }
    }
    
    try:
        doc_ref = db.collection('notifications_draft').add(test_draft)
        doc_id = doc_ref[1].id
        
        print("✅ Test draft notification added successfully!")
        print(f"📄 Document ID: {doc_id}")
        print("📊 Collection: notifications_draft")
        print(f"📝 Title: {test_draft['title']}")
        print("\n🔄 Refresh your admin dashboard to see this notification in the queue!")
        return 0
    except Exception as e:
        print(f"❌ Error adding test draft: {e}")
        return 1

if __name__ == '__main__':
    exit(add_test_draft())
