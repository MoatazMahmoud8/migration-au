import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:purchases_flutter/purchases_flutter.dart';

import 'core/router/app_router.dart';
import 'core/services/fcm_service.dart';
import 'core/theme/app_theme.dart';
import 'features/ai_assistant/cubit/ai_cubit.dart';
import 'features/points_calculator/cubit/calculator_cubit.dart';
import 'features/profile/cubit/profile_cubit.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Firebase
  await Firebase.initializeApp();

  // FCM
  await FcmService.initialize();

  // RevenueCat
  await Purchases.configure(
    PurchasesConfiguration('YOUR_REVENUECAT_PUBLIC_KEY'),
  );

  runApp(const MigrationAuApp());
}

class MigrationAuApp extends StatelessWidget {
  const MigrationAuApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiBlocProvider(
      providers: [
        BlocProvider(create: (_) => CalculatorCubit()),
        BlocProvider(create: (_) => AiCubit()),
        BlocProvider(create: (_) => ProfileCubit()..loadProfile()),
      ],
      child: MaterialApp.router(
        title: 'MigrateAU',
        theme: AppTheme.light,
        routerConfig: AppRouter.router,
        debugShowCheckedModeBanner: false,
      ),
    );
  }
}
