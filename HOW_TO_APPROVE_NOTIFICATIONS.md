# ✅ HOW TO APPROVE NOTIFICATIONS

**Dashboard**: https://swift-shore-238707.web.app/login  
**Status**: ✅ **Ready for Sign-In**

---

## 🔐 STEP 1: Sign In to Dashboard

1. **Go to**: https://swift-shore-238707.web.app/login
2. **Click**: "Sign in with Google" button
3. **Select**: Your Google account
4. **Wait**: 5-10 seconds for authentication
5. **Result**: Should redirect to `/admin/dashboard`

---

## 📋 STEP 2: View Draft Notifications

Once signed in, you'll see:
- **Page Title**: "Draft Notifications"
- **List**: All notifications waiting for approval
- **Info Per Notification**:
  - Title
  - Body/Description
  - State (e.g., VIC, NSW)
  - Created date
  - Action buttons

---

## ✅ STEP 3: Approve Notification

For each notification:

1. **Find notification** in the list
2. **Click**: Green "✅ Approve" button
3. **Confirm**: In popup dialog (if shown)
4. **Wait**: ~1-2 seconds for processing
5. **Expected Result**:
   - Notification disappears from list
   - Cloud Function executes automatically
   - FCM trigger created
   - FCM message sent to mobile

---

## 🎯 What Happens When You Approve

```
YOU: Click "Approve" Button
    ↓ (1 second)
approveNotification Cloud Function
    ↓
1. Moves notification to "published" collection
2. Creates FCM trigger document
    ↓ (~2 seconds)
processFcmTrigger Cloud Function
    ↓
1. Reads FCM trigger
2. Sends message via FCM API
    ↓ (~5 seconds)
Mobile App Receives Notification 📱
    ↓
User Sees: "📰 New {STATE} Migration Update"
```

**Total Time**: < 10 seconds

---

## 🔄 WHAT IF THERE ARE NO NOTIFICATIONS?

If draft list is empty:

1. **Scraper hasn't found articles yet**
   - Scrapers look for NEW articles (not repeats)
   - State websites may be returning errors
   - Check: Cloud Function logs for scraper results

2. **Articles are being processed**
   - Wait 5+ minutes for scraper to complete
   - Reload dashboard

3. **Create test notification manually**
   - Firebase Console → notifications_draft
   - Add document with `status: "draft"`
   - Refresh dashboard
   - Approve it

---

## 📊 MONITORING APPROVAL

### After Clicking Approve:

**Check Firestore**:
```
1. notifications_draft
   → Your notification should disappear

2. notifications
   → New document should appear with "status: published"

3. fcm_triggers
   → New trigger document should exist
   → Should show "sent: true"
```

**Check Cloud Function Logs**:
```
gcloud functions logs read approveNotification \
  --project swift-shore-238707 \
  --limit 20
  
gcloud functions logs read processFcmTrigger \
  --project swift-shore-238707 \
  --limit 20
```

**Check Mobile**:
```
1. Open Expo/TestFlight app
2. Check notification center
3. Should see: "📰 New {STATE} Migration Update"
4. Tap to open article link
```

---

## ❌ TROUBLESHOOTING

### Approval Button Not Responding
- ✅ **Solution**: Reload dashboard and try again
- ✅ Check browser console for errors (F12)
- ✅ Verify admin claims are set (see below)

### Notification Not Moving to Published
- ✅ **Check**: Cloud Function logs for errors
- ✅ **Check**: Firestore write permissions
- ✅ **Check**: Admin role verified

### FCM Not Sending
- ✅ **Check**: FCM trigger document created
- ✅ **Check**: Topics configured correctly  
- ✅ **Check**: processFcmTrigger function logs

### Mobile Not Receiving
- ✅ **Check**: App has notification permission
- ✅ **Check**: App is subscribed to topics
- ✅ **Check**: FCM trigger shows "sent: true"
- ✅ **Check**: Device is connected to internet

---

## 🆙 HOW TO SET ADMIN CLAIMS (If Sign-In Fails)

If you get "Admin access required" error:

```bash
# Method 1: Use Custom Claims Script
cd repo && firebase auth:import \
  --project swift-shore-238707 \
  --uid "YOUR_USER_UID" \
  --email "your-email@gmail.com" \
  --custom-claims '{"admin":true}'

# Method 2: Set via Firestore Custom Claims
gcloud firestore documents update users/YOUR_UID \
  --project swift-shore-238707 \
  --update customClaims.admin=true
```

To get your UID:
1. Go to Firebase Console
2. Authentication → Users
3. Find your email
4. Copy the UID

---

## 🎉 SUCCESS CRITERIA

✅ Sign in works  
✅ See draft notifications  
✅ Approve button responds  
✅ Notification moved to published  
✅ FCM trigger created  
✅ Mobile receives notification  
✅ Notification displays with correct title/body  

---

## 📞 QUICK HELP

| Issue | Solution |
|-------|----------|
| **404 on dashboard** | Wait 30 seconds for cache to clear, hard refresh (Ctrl+Shift+R) |
| **Can't sign in** | Check Gmail is correct account, verify admin claims set |
| **No draft notifications** | Create one manually or wait for scraper to find articles |
| **Approval fails silently** | Check console (F12), reload page, try again |
| **Mobile not getting notif** | Check app permissions, restart app, verify subscribed to topics |

---

## 🚀 READY TO TEST?

1. ✅ Go to: https://swift-shore-238707.web.app/login
2. ✅ Click: "Sign in with Google"
3. ✅ Select your account
4. ✅ Wait for dashboard to load
5. ✅ Find notifications in draft list
6. ✅ Click: "Approve"
7. ✅ Check mobile for notification

**Expected total time**: 5 minutes

---

**Good luck! 🎯 Let me know if you need help with any step.**

