/// Centralised runtime configuration.
///
/// All sensitive keys are injected at build time via `--dart-define`.
/// Never hardcode real keys here — use placeholder strings only.
///
/// Build command example:
///   flutter run \
///     --dart-define=GEMINI_API_KEY=AIza... \
///     --dart-define=REVENUECAT_PUBLIC_KEY=appl_...
///
/// CI / GitHub Actions example (add to workflow env):
///   flutter build appbundle \
///     --dart-define=GEMINI_API_KEY=${{ secrets.GEMINI_API_KEY }} \
///     --dart-define=REVENUECAT_PUBLIC_KEY=${{ secrets.REVENUECAT_PUBLIC_KEY }}
abstract class AppConfig {
  // ---------------------------------------------------------------------------
  // Google Gemini
  // ---------------------------------------------------------------------------
  static const String geminiApiKey = String.fromEnvironment(
    'GEMINI_API_KEY',
    defaultValue: '',
  );

  // ---------------------------------------------------------------------------
  // RevenueCat
  // ---------------------------------------------------------------------------
  static const String revenueCatPublicKey = String.fromEnvironment(
    'REVENUECAT_PUBLIC_KEY',
    defaultValue: '',
  );

  // ---------------------------------------------------------------------------
  // Validation (call once at startup)
  // ---------------------------------------------------------------------------
  static void assertKeysPresent() {
    assert(
      geminiApiKey.isNotEmpty,
      'GEMINI_API_KEY is not set. '
      'Pass it via --dart-define=GEMINI_API_KEY=<your_key>',
    );
    assert(
      revenueCatPublicKey.isNotEmpty,
      'REVENUECAT_PUBLIC_KEY is not set. '
      'Pass it via --dart-define=REVENUECAT_PUBLIC_KEY=<your_key>',
    );
  }
}
