import 'package:flutter/material.dart';

abstract class AppColors {
  /// Primary — Deep Government Blue
  static const Color primary = Color(0xFF002D62);
  static const Color primaryLight = Color(0xFF1A4A8A);
  static const Color primaryDark = Color(0xFF001A3D);

  /// Secondary — Australian Gold
  static const Color secondary = Color(0xFFFFCD00);
  static const Color secondaryDark = Color(0xFFC9A200);

  /// Neutrals
  static const Color surface = Color(0xFFFFFFFF);
  static const Color background = Color(0xFFF4F6FA);
  static const Color onSurface = Color(0xFF1A1A2E);
  static const Color onBackground = Color(0xFF1A1A2E);

  static const Color textPrimary = Color(0xFF1A1A2E);
  static const Color textSecondary = Color(0xFF5A6070);
  static const Color textHint = Color(0xFF9AA0AD);

  static const Color divider = Color(0xFFE5E8EF);
  static const Color border = Color(0xFFCDD1DA);

  /// Status
  static const Color success = Color(0xFF00875A);
  static const Color warning = Color(0xFFFF8B00);
  static const Color error = Color(0xFFDE350B);
  static const Color info = Color(0xFF0052CC);

  /// Score tiers
  static const Color scoreLow = Color(0xFFDE350B);
  static const Color scoreMedium = Color(0xFFFF8B00);
  static const Color scoreHigh = Color(0xFF00875A);
}

class AppTheme {
  AppTheme._();

  static ThemeData get light => ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.primary,
          primary: AppColors.primary,
          secondary: AppColors.secondary,
          surface: AppColors.surface,
          error: AppColors.error,
        ),
        scaffoldBackgroundColor: AppColors.background,
        fontFamily: 'Inter',
        appBarTheme: const AppBarTheme(
          backgroundColor: AppColors.primary,
          foregroundColor: Colors.white,
          elevation: 0,
          centerTitle: false,
          titleTextStyle: TextStyle(
            fontFamily: 'Inter',
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: Colors.white,
          ),
        ),
        bottomNavigationBarTheme: const BottomNavigationBarThemeData(
          backgroundColor: AppColors.surface,
          selectedItemColor: AppColors.primary,
          unselectedItemColor: AppColors.textHint,
          type: BottomNavigationBarType.fixed,
          elevation: 8,
          selectedLabelStyle: TextStyle(
            fontFamily: 'Inter',
            fontSize: 11,
            fontWeight: FontWeight.w600,
          ),
          unselectedLabelStyle: TextStyle(
            fontFamily: 'Inter',
            fontSize: 11,
          ),
        ),
        cardTheme: CardTheme(
          color: AppColors.surface,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: const BorderSide(color: AppColors.divider),
          ),
          margin: EdgeInsets.zero,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.primary,
            foregroundColor: Colors.white,
            elevation: 0,
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
            textStyle: const TextStyle(
              fontFamily: 'Inter',
              fontSize: 15,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            foregroundColor: AppColors.primary,
            side: const BorderSide(color: AppColors.primary),
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: AppColors.surface,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: AppColors.border),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: AppColors.border),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: AppColors.primary, width: 2),
          ),
          labelStyle: const TextStyle(
            color: AppColors.textSecondary,
            fontFamily: 'Inter',
          ),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 14,
          ),
        ),
        textTheme: const TextTheme(
          displayLarge: TextStyle(
            fontSize: 32,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
            height: 1.2,
          ),
          displayMedium: TextStyle(
            fontSize: 26,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
            height: 1.25,
          ),
          headlineMedium: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
          titleLarge: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
          titleMedium: TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w500,
            color: AppColors.textPrimary,
          ),
          bodyLarge: TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w400,
            color: AppColors.textPrimary,
            height: 1.5,
          ),
          bodyMedium: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w400,
            color: AppColors.textSecondary,
            height: 1.5,
          ),
          labelLarge: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
        ),
      );
}
