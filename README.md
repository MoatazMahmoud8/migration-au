# MigrateAU — Australian Skilled Migration App

A production-ready Flutter + Firebase app for Australian General Skilled Migration (GSM) visa applicants. Covers **Subclass 189, 190, and 491** with a real-time points calculator, state nomination tracker, AI immigration consultant (Gemini), and push notifications via FCM.

---

## Architecture

```
lib/
├── core/
│   ├── router/         # GoRouter shell + bottom nav
│   ├── services/       # FCM service
│   └── theme/          # AppColors + AppTheme (Gov-tech: #002D62 / #FFCD00)
└── features/
    ├── home/           # News feed dashboard
    ├── points_calculator/
    │   ├── cubit/      # CalculatorCubit + CalculatorState
    │   ├── models/
    │   ├── screens/    # CalculatorScreen
    │   └── services/   # PointsCalculatorService (pure Dart logic)
    ├── states/
    │   └── screens/    # StatesScreen (Firestore stream + FCM subscribe)
    ├── ai_assistant/
    │   ├── cubit/      # AiCubit + AiState
    │   ├── screens/    # AiAssistantScreen (chat UI)
    │   └── services/   # AiConsultantService (Gemini)
    └── profile/
        ├── cubit/      # ProfileCubit + ProfileState
        └── screens/    # ProfileScreen + PaywallScreen (RevenueCat)

scripts/
├── state_news_scraper.py   # Python scraper → Firestore
└── requirements.txt

.github/workflows/
└── scraper.yml             # Daily cron job (GitHub Actions)
```

---

## Quick Start

### Prerequisites
- Flutter 3.x SDK
- Firebase project (Firestore, Auth, FCM enabled)
- Google Gemini API key
- RevenueCat account + entitlement configured

### 1. Clone and install
```bash
git clone https://github.com/YOUR_ORG/migration-au.git
cd migration-au/repo
flutter pub get
```

### 2. Configure Firebase
```bash
# Install FlutterFire CLI if not already installed
dart pub global activate flutterfire_cli

# Configure — follow prompts to select your Firebase project
flutterfire configure
```
This generates `lib/firebase_options.dart`. Update `main.dart` to pass it:
```dart
await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
```

### 3. Set API keys
- **Gemini**: Pass via `--dart-define=GEMINI_API_KEY=YOUR_KEY` at build time, or use a remote config solution.
- **RevenueCat**: Replace `'YOUR_REVENUECAT_PUBLIC_KEY'` in `main.dart`.

### 4. Run the app
```bash
flutter run --dart-define=GEMINI_API_KEY=YOUR_KEY
```

---

## Points Calculator

`lib/features/points_calculator/services/points_calculator_service.dart`

Pure Dart implementation of the Department of Home Affairs SkillSelect points test.

| Category | Max Points |
|----------|-----------|
| Age (25–32 = 30 pts) | 30 |
| English (Superior = 20 pts) | 20 |
| Australian Work Experience | 20 |
| Overseas Work Experience | 15 |
| Partner Skills | 10 |
| State/Territory Nomination (491 = 15, 190 = 5) | 15 |
| Professional Year | 5 |
| NAATI CCL | 5 |
| Community Language | 5 |
| Australian Study | 5 |
| **Maximum** | **130** |

---

## Deploying the Scraper via GitHub Actions

### How it works
1. The workflow in `.github/workflows/scraper.yml` triggers daily at **02:00 UTC**.
2. It runs `scripts/state_news_scraper.py`, which fetches the latest migration news from configured state government pages.
3. New articles are written to the **`news`** Firestore collection.
4. If a new article is found for a state, an FCM notification is sent to the relevant **`State_<CODE>`** topic.

### Required GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|--------|-------------|
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Full JSON content of a Firebase Admin SDK service account key |
| `FIREBASE_PROJECT_ID` | Your Firebase project ID (e.g. `migration-au-prod`) |
| `FCM_SERVER_KEY` | FCM legacy server key (found in Firebase Console → Project Settings → Cloud Messaging) |

### Generating a Service Account Key
1. Go to [Firebase Console](https://console.firebase.google.com) → Project Settings → Service Accounts.
2. Click **Generate new private key**.
3. Copy the entire JSON file content into the `FIREBASE_SERVICE_ACCOUNT_JSON` secret.

### Manual trigger
You can run the scraper on demand from **Actions → Run State News Scraper → Run workflow**.

---

## Firestore Schema

### `news` collection
```
news/{docId}
  title:       string   — Headline
  summary:     string   — Short description (1–2 sentences)
  url:         string   — Original article URL
  state:       string   — State code: NSW | VIC | QLD | WA | SA | TAS | ACT | NT | NATIONAL
  source:      string   — Source site name
  publishedAt: timestamp
  scrapedAt:   timestamp
  notified:    boolean  — Whether FCM notification was sent
```

### `users` collection (optional — if Auth is added)
```
users/{uid}
  displayName:    string
  anzscoCode:     string
  subscribedTopics: string[]
  isPremium:      boolean
  premiumExpiry:  timestamp
```

---

## Monetization (RevenueCat)

The `PaywallScreen` (`lib/features/profile/screens/paywall_screen.dart`) handles:
- Display of subscription options
- Purchasing via `Purchases.purchasePackage()`
- Restoring purchases via `Purchases.restorePurchases()`

**Required RevenueCat setup:**
1. Create a product in Google Play Console: `migration_au_premium_monthly` and `migration_au_premium_yearly`.
2. Create an entitlement `premium` in RevenueCat dashboard linked to both products.
3. Create an offering `default` with both packages.

---

## AI Assistant (Gemini)

`lib/features/ai_assistant/services/ai_consultant_service.dart`

- Uses `gemini-1.5-pro` with a custom system prompt as "Aria" — an Australian immigration consultant.
- On session start, fetches the 5 most recent Firestore `news` docs and injects them as context.
- Maintains conversation history within a `ChatSession`.
- Gracefully handles `GenerativeAIException` errors.

---

## Color Palette

| Token | Hex | Usage |
|-------|-----|-------|
| `primary` | `#002D62` | App bar, buttons, headings |
| `secondary` | `#FFCD00` | Accent, CTAs, premium badges |
| `background` | `#F4F6FA` | Scaffold background |
| `success` | `#00875A` | High score, eligible indicator |
| `warning` | `#FF8B00` | Medium score |
| `error` | `#DE350B` | Low score, errors |

---

## Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Run tests: `flutter test`
3. Ensure analysis passes: `flutter analyze`
4. Open a pull request.

---

## License

Proprietary — All rights reserved.
