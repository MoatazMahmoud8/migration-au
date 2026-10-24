/**
 * Purge Stale Content Changes Script
 * Scans pending_content_changes and deletes non-official items
 * Unllinks orphaned notification drafts and converts to standalone drafts
 * 
 * Usage: npx ts-node scripts/purge_stale_content_changes.ts [--dry-run]
 */

import * as admin from 'firebase-admin';
import * as serviceAccount from '../service-account.json';

const dryRun = process.argv.includes('--dry-run');

// Initialize Firebase Admin
admin.initializeApp({
  credential: admin.credential.cert(serviceAccount as admin.ServiceAccount),
  projectId: process.env.FIREBASE_PROJECT_ID || serviceAccount.project_id,
});

const db = admin.firestore();

interface ContentChange {
  id: string;
  is_official: boolean;
  source_type: string;
  status: string;
  notification_draft_id?: string;
  created_at: admin.firestore.Timestamp;
}

interface PurgeResult {
  scanned: number;
  deleted: number;
  draftCleaned: number;
  errors: string[];
}

async function purgeStalePendingContentChanges(): Promise<PurgeResult> {
  const result: PurgeResult = {
    scanned: 0,
    deleted: 0,
    draftCleaned: 0,
    errors: [],
  };

  console.log(`\n🧹 Starting purge of stale content changes (dry-run: ${dryRun})...\n`);

  try {
    // Scan pending_content_changes where status = pending
    const query = db
      .collection('pending_content_changes')
      .where('status', '==', 'pending');

    const snapshot = await query.get();

    console.log(`📊 Found ${snapshot.size} pending content changes to review\n`);

    for (const doc of snapshot.docs) {
      const data = doc.data() as ContentChange;
      result.scanned++;

      // Check if this should be deleted
      const isNonOfficial = data.is_official === false;
      const isNewsRss = data.source_type === 'news_rss';
      const shouldDelete = isNonOfficial || isNewsRss;

      if (shouldDelete) {
        const reason = isNonOfficial 
          ? 'non-official source'
          : isNewsRss 
          ? 'news_rss source type'
          : 'unknown';

        console.log(`🗑️  [${result.deleted + 1}] Deleting: ${doc.id}`);
        console.log(`   Reason: ${reason}`);
        console.log(`   is_official: ${data.is_official}, source_type: ${data.source_type}\n`);

        if (!dryRun) {
          // If linked to a notification draft, unlink it
          if (data.notification_draft_id) {
            try {
              const draftRef = db.collection('notifications_draft').doc(data.notification_draft_id);
              await draftRef.update({
                contentChangeId: admin.firestore.FieldValue.delete(),
                contentChangeStatus: admin.firestore.FieldValue.delete(),
                updatedAt: admin.firestore.Timestamp.now(),
              });
              result.draftCleaned++;
              console.log(`   ↳ Unlinked from draft ${data.notification_draft_id}`);
            } catch (err) {
              result.errors.push(
                `Failed to unlink draft ${data.notification_draft_id}: ${err}`
              );
            }
          }

          // Write history record
          try {
            await db.collection('content_change_history').add({
              original_id: doc.id,
              original_data: data,
              reason: `auto-purged: ${reason}`,
              purged_at: admin.firestore.Timestamp.now(),
            });
          } catch (err) {
            result.errors.push(`Failed to write history for ${doc.id}: ${err}`);
          }

          // Delete the document
          await db.collection('pending_content_changes').doc(doc.id).delete();
          result.deleted++;
        }
      }
    }

    console.log(`\n✅ Purge complete!`);
    console.log(`   Scanned: ${result.scanned}`);
    console.log(`   Deleted: ${result.deleted}`);
    console.log(`   Drafts cleaned: ${result.draftCleaned}`);

    if (result.errors.length > 0) {
      console.log(`   Errors: ${result.errors.length}`);
      result.errors.forEach((err) => console.log(`     - ${err}`));
    }

    if (dryRun) {
      console.log(`\n🔒 DRY RUN - no changes made. Run without --dry-run to apply.\n`);
    }

    return result;
  } catch (err) {
    console.error('❌ Error during purge:', err);
    throw err;
  }
}

async function main() {
  try {
    const result = await purgeStalePendingContentChanges();
    
    if (!dryRun) {
      console.log(`\n📝 Results saved to content_change_history collection`);
    }
    
    process.exit(result.errors.length > 0 ? 1 : 0);
  } catch (err) {
    console.error('Fatal error:', err);
    process.exit(1);
  }
}

main();
