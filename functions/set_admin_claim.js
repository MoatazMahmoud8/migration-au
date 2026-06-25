const admin = require("firebase-admin");

admin.initializeApp({
  projectId: "swift-shore-238707"
});

async function setAdminClaim(uid) {
  try {
    await admin.auth().setCustomUserClaims(uid, { admin: true });
    console.log(`✅ Admin claim set successfully for ${uid}`);
    console.log(`Custom Claims: { "admin": true }`);
    process.exit(0);
  } catch (error) {
    console.error(`❌ Error setting admin claim:`, error.message);
    process.exit(1);
  }
}

setAdminClaim("3zzpA0g5aWMYreS5b4Ye1hW38O22");
