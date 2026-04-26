import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../features/ai_assistant/screens/ai_assistant_screen.dart';
import '../../features/home/screens/home_screen.dart';
import '../../features/points_calculator/screens/calculator_screen.dart';
import '../../features/profile/screens/profile_screen.dart';
import '../../features/states/screens/states_screen.dart';

abstract class AppRouter {
  static final router = GoRouter(
    initialLocation: '/home',
    routes: [
      ShellRoute(
        builder: (context, state, child) => MainScaffold(child: child),
        routes: [
          GoRoute(
            path: '/home',
            builder: (context, state) => const HomeScreen(),
          ),
          GoRoute(
            path: '/points',
            builder: (context, state) => const CalculatorScreen(),
          ),
          GoRoute(
            path: '/states',
            builder: (context, state) => const StatesScreen(),
          ),
          GoRoute(
            path: '/ai',
            builder: (context, state) => const AiAssistantScreen(),
          ),
          GoRoute(
            path: '/profile',
            builder: (context, state) => const ProfileScreen(),
          ),
        ],
      ),
    ],
  );
}

class MainScaffold extends StatelessWidget {
  const MainScaffold({super.key, required this.child});

  final Widget child;

  int _locationToIndex(String location) {
    if (location.startsWith('/home')) return 0;
    if (location.startsWith('/points')) return 1;
    if (location.startsWith('/states')) return 2;
    if (location.startsWith('/ai')) return 3;
    if (location.startsWith('/profile')) return 4;
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).uri.toString();

    return Scaffold(
      body: child,
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _locationToIndex(location),
        onTap: (index) {
          switch (index) {
            case 0:
              context.go('/home');
            case 1:
              context.go('/points');
            case 2:
              context.go('/states');
            case 3:
              context.go('/ai');
            case 4:
              context.go('/profile');
          }
        },
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home_outlined),
            activeIcon: Icon(Icons.home),
            label: 'Home',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.calculate_outlined),
            activeIcon: Icon(Icons.calculate),
            label: 'Points',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.map_outlined),
            activeIcon: Icon(Icons.map),
            label: 'States',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.smart_toy_outlined),
            activeIcon: Icon(Icons.smart_toy),
            label: 'AI',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.person_outline),
            activeIcon: Icon(Icons.person),
            label: 'Profile',
          ),
        ],
      ),
    );
  }
}
