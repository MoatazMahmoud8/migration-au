import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';

import '../../../core/services/fcm_service.dart';
import '../../../core/theme/app_theme.dart';

class StatesScreen extends StatelessWidget {
  const StatesScreen({super.key});

  static const List<_StateInfo> _states = [
    _StateInfo(code: 'NSW', name: 'New South Wales', flag: '🦁'),
    _StateInfo(code: 'VIC', name: 'Victoria', flag: '⭐'),
    _StateInfo(code: 'QLD', name: 'Queensland', flag: '🌞'),
    _StateInfo(code: 'WA', name: 'Western Australia', flag: '🦅'),
    _StateInfo(code: 'SA', name: 'South Australia', flag: '🐦'),
    _StateInfo(code: 'TAS', name: 'Tasmania', flag: '🦘'),
    _StateInfo(code: 'ACT', name: 'Aust. Capital Territory', flag: '🏛'),
    _StateInfo(code: 'NT', name: 'Northern Territory', flag: '🌵'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('State Nominations'),
        actions: [
          IconButton(
            icon: const Icon(Icons.info_outline),
            tooltip: 'About state nominations',
            onPressed: () => _showInfoDialog(context),
          ),
        ],
      ),
      body: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _states.length,
        itemBuilder: (context, index) =>
            _StateCard(state: _states[index]),
      ),
    );
  }

  void _showInfoDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('State Nominations'),
        content: const Text(
          'State and Territory nominations allow you to apply for a Subclass 190 or 491 visa. '
          'Enable notifications to be alerted when your occupation opens in a state.\n\n'
          'Data is refreshed daily via our automated scraper.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Got it'),
          ),
        ],
      ),
    );
  }
}

class _StateCard extends StatefulWidget {
  const _StateCard({required this.state});

  final _StateInfo state;

  @override
  State<_StateCard> createState() => _StateCardState();
}

class _StateCardState extends State<_StateCard> {
  bool _notificationsEnabled = false;

  Future<void> _toggleNotifications() async {
    if (_notificationsEnabled) {
      await FcmService.unsubscribeFromState(widget.state.code);
    } else {
      await FcmService.subscribeToState(widget.state.code);
    }
    setState(() => _notificationsEnabled = !_notificationsEnabled);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: ExpansionTile(
        leading: Text(
          widget.state.flag,
          style: const TextStyle(fontSize: 28),
        ),
        title: Text(
          widget.state.name,
          style: const TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 15,
            color: AppColors.textPrimary,
          ),
        ),
        subtitle: Text(
          widget.state.code,
          style: const TextStyle(
            fontSize: 12,
            color: AppColors.textSecondary,
          ),
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              icon: Icon(
                _notificationsEnabled
                    ? Icons.notifications_active
                    : Icons.notifications_none,
                color: _notificationsEnabled
                    ? AppColors.secondary
                    : AppColors.textHint,
              ),
              onPressed: _toggleNotifications,
              tooltip: _notificationsEnabled
                  ? 'Disable notifications'
                  : 'Enable notifications',
            ),
          ],
        ),
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: _StateNewsStream(stateCode: widget.state.code),
          ),
        ],
      ),
    );
  }
}

class _StateNewsStream extends StatelessWidget {
  const _StateNewsStream({required this.stateCode});

  final String stateCode;

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<QuerySnapshot>(
      stream: FirebaseFirestore.instance
          .collection('news')
          .where('state', isEqualTo: stateCode)
          .orderBy('publishedAt', descending: true)
          .limit(3)
          .snapshots(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Padding(
            padding: EdgeInsets.all(12),
            child: Center(child: CircularProgressIndicator()),
          );
        }

        final docs = snapshot.data?.docs ?? [];
        if (docs.isEmpty) {
          return const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text(
              'No recent news for this state.',
              style: TextStyle(color: AppColors.textHint, fontSize: 13),
            ),
          );
        }

        return Column(
          children: docs.map((doc) {
            final data = doc.data() as Map<String, dynamic>;
            return _NewsItem(
              title: data['title'] ?? '',
              summary: data['summary'] ?? '',
              publishedAt:
                  (data['publishedAt'] as Timestamp?)?.toDate(),
              url: data['url'] as String?,
            );
          }).toList(),
        );
      },
    );
  }
}

class _NewsItem extends StatelessWidget {
  const _NewsItem({
    required this.title,
    required this.summary,
    this.publishedAt,
    this.url,
  });

  final String title;
  final String summary;
  final DateTime? publishedAt;
  final String? url;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: AppColors.textPrimary,
            ),
          ),
          if (summary.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              summary,
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.textSecondary,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          if (publishedAt != null) ...[
            const SizedBox(height: 4),
            Text(
              '${publishedAt!.day}/${publishedAt!.month}/${publishedAt!.year}',
              style: const TextStyle(
                fontSize: 11,
                color: AppColors.textHint,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _StateInfo {
  const _StateInfo({
    required this.code,
    required this.name,
    required this.flag,
  });

  final String code;
  final String name;
  final String flag;
}
