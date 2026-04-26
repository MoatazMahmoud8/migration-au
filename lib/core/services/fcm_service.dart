import 'dart:developer';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

/// Handles Firebase Cloud Messaging initialization and topic-based subscriptions.
///
/// Topic naming conventions:
/// - Occupation alerts: `Occupation_<ANZSCO>` e.g. `Occupation_261313`
/// - State/Territory alerts: `State_<CODE>` e.g. `State_VIC`, `State_NSW`
/// - General news: `General_News`
class FcmService {
  FcmService._();

  static final _messaging = FirebaseMessaging.instance;

  /// Call once at app startup (in main.dart before runApp)
  static Future<void> initialize() async {
    // Request permission (iOS + Android 13+)
    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      provisional: false,
    );

    if (kDebugMode) {
      log('FCM permission: ${settings.authorizationStatus}');
    }

    // Always subscribe to general news
    await subscribeToTopic('General_News');

    // Handle messages when app is in foreground
    FirebaseMessaging.onMessage.listen(_handleForegroundMessage);

    // Handle notification tap when app is in background (but open)
    FirebaseMessaging.onMessageOpenedApp.listen(_handleMessageOpenedApp);

    // Handle notification that launched a terminated app
    final initialMessage = await _messaging.getInitialMessage();
    if (initialMessage != null) {
      _handleMessageOpenedApp(initialMessage);
    }

    // Background message handler must be a top-level function
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);
  }

  // ---------------------------------------------------------------------------
  // Topic Subscription
  // ---------------------------------------------------------------------------

  /// Subscribe to notifications for a specific ANZSCO occupation code.
  /// Example: subscribeToOccupation('261313')
  static Future<void> subscribeToOccupation(String anzscoCode) async {
    final topic = 'Occupation_$anzscoCode';
    await subscribeToTopic(topic);
    log('FCM: subscribed to $topic');
  }

  /// Unsubscribe from occupation notifications
  static Future<void> unsubscribeFromOccupation(String anzscoCode) async {
    final topic = 'Occupation_$anzscoCode';
    await unsubscribeFromTopic(topic);
    log('FCM: unsubscribed from $topic');
  }

  /// Subscribe to notifications for a specific state/territory.
  /// Example: subscribeToState('VIC')
  static Future<void> subscribeToState(String stateCode) async {
    final topic = 'State_$stateCode';
    await subscribeToTopic(topic);
    log('FCM: subscribed to $topic');
  }

  /// Unsubscribe from state notifications
  static Future<void> unsubscribeFromState(String stateCode) async {
    final topic = 'State_$stateCode';
    await unsubscribeFromTopic(topic);
    log('FCM: unsubscribed from $topic');
  }

  static Future<void> subscribeToTopic(String topic) async {
    await _messaging.subscribeToTopic(topic);
  }

  static Future<void> unsubscribeFromTopic(String topic) async {
    await _messaging.unsubscribeFromTopic(topic);
  }

  // ---------------------------------------------------------------------------
  // Token
  // ---------------------------------------------------------------------------

  /// Get the device FCM token (useful for targeted push from server)
  static Future<String?> getToken() async {
    return _messaging.getToken();
  }

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  static void _handleForegroundMessage(RemoteMessage message) {
    log('FCM foreground: ${message.notification?.title}');
    // TODO: Show in-app notification banner (use overlay or local notification)
  }

  static void _handleMessageOpenedApp(RemoteMessage message) {
    log('FCM opened: ${message.data}');
    // TODO: Navigate based on message.data['route'] or message.data['type']
    // e.g. if data['type'] == 'occupation', navigate to /states
  }
}

/// Top-level background message handler (must be outside class)
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  log('FCM background: ${message.notification?.title}');
}
