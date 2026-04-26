import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../core/services/fcm_service.dart';
import '../../../core/theme/app_theme.dart';
import '../cubit/profile_cubit.dart';
import 'paywall_screen.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: BlocBuilder<ProfileCubit, ProfileState>(
        builder: (context, state) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _ProfileHeader(name: state.name, isPremium: state.isPremium),
              const SizedBox(height: 20),

              // Premium Banner
              if (!state.isPremium)
                _PremiumBanner(
                  onUpgrade: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const PaywallScreen(),
                    ),
                  ),
                ),

              const SizedBox(height: 20),

              // Settings sections
              _SettingsSection(
                title: 'Occupation Tracking',
                children: [
                  _AnzscoTile(
                    current: state.anzscoCode,
                    onSave: context.read<ProfileCubit>().updateAnzsco,
                    isPremium: state.isPremium,
                    onUpgrade: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => const PaywallScreen(),
                      ),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 16),

              _SettingsSection(
                title: 'Notifications',
                children: [
                  ListTile(
                    leading: const Icon(Icons.notifications_active,
                        color: AppColors.primary),
                    title: const Text('General Migration News'),
                    subtitle: const Text('Always enabled'),
                    trailing: Switch.adaptive(
                      value: true,
                      onChanged: null,
                      activeColor: AppColors.primary,
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 16),

              _SettingsSection(
                title: 'About',
                children: [
                  ListTile(
                    leading: const Icon(Icons.info_outline,
                        color: AppColors.primary),
                    title: const Text('Version'),
                    trailing: const Text(
                      '1.0.0',
                      style: TextStyle(color: AppColors.textSecondary),
                    ),
                  ),
                  ListTile(
                    leading: const Icon(Icons.policy_outlined,
                        color: AppColors.primary),
                    title: const Text('Privacy Policy'),
                    trailing: const Icon(Icons.arrow_forward_ios,
                        size: 14, color: AppColors.textHint),
                    onTap: () {},
                  ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}

class _ProfileHeader extends StatelessWidget {
  const _ProfileHeader({required this.name, required this.isPremium});

  final String name;
  final bool isPremium;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        CircleAvatar(
          radius: 32,
          backgroundColor: AppColors.primary,
          child: Text(
            name.isNotEmpty ? name[0].toUpperCase() : 'U',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 24,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                name.isNotEmpty ? name : 'Skilled Migrant',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(height: 4),
              if (isPremium)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.secondary,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text(
                    'PREMIUM',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      color: AppColors.primary,
                    ),
                  ),
                )
              else
                const Text(
                  'Free Plan',
                  style: TextStyle(
                    fontSize: 13,
                    color: AppColors.textSecondary,
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

class _PremiumBanner extends StatelessWidget {
  const _PremiumBanner({required this.onUpgrade});

  final VoidCallback onUpgrade;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppColors.primary, AppColors.primaryLight],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Upgrade to Premium',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  'Get occupation alerts, AI consultant & round history.',
                  style: TextStyle(color: Colors.white70, fontSize: 12),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          ElevatedButton(
            onPressed: onUpgrade,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.secondary,
              foregroundColor: AppColors.primary,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            child: const Text(
              'Upgrade',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
    );
  }
}

class _SettingsSection extends StatelessWidget {
  const _SettingsSection({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 8),
          child: Text(
            title.toUpperCase(),
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.bold,
              color: AppColors.textHint,
              letterSpacing: 1.2,
            ),
          ),
        ),
        Container(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.border),
          ),
          child: Column(children: children),
        ),
      ],
    );
  }
}

class _AnzscoTile extends StatelessWidget {
  const _AnzscoTile({
    required this.current,
    required this.onSave,
    required this.isPremium,
    required this.onUpgrade,
  });

  final String current;
  final ValueChanged<String> onSave;
  final bool isPremium;
  final VoidCallback onUpgrade;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: const Icon(Icons.work_outline, color: AppColors.primary),
      title: const Text('ANZSCO Occupation Code'),
      subtitle: Text(
        current.isNotEmpty ? current : 'e.g. 261313 (Software Engineer)',
        style: TextStyle(
          color:
              current.isNotEmpty ? AppColors.textPrimary : AppColors.textHint,
        ),
      ),
      trailing: isPremium
          ? const Icon(Icons.edit, size: 18, color: AppColors.textHint)
          : const Icon(Icons.lock, size: 18, color: AppColors.textHint),
      onTap: () {
        if (!isPremium) {
          onUpgrade();
          return;
        }
        _showEditDialog(context);
      },
    );
  }

  void _showEditDialog(BuildContext context) {
    final ctrl = TextEditingController(text: current);
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('ANZSCO Code'),
        content: TextField(
          controller: ctrl,
          keyboardType: TextInputType.number,
          maxLength: 6,
          decoration: const InputDecoration(
            labelText: 'Enter 6-digit ANZSCO code',
            hintText: '261313',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              onSave(ctrl.text.trim());
              Navigator.pop(context);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }
}
