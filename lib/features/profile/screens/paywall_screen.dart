import 'dart:developer';

import 'package:flutter/material.dart';
import 'package:purchases_flutter/purchases_flutter.dart';

import '../../../core/theme/app_theme.dart';

/// Premium paywall screen using RevenueCat.
/// Shows subscription options and handles purchase flow.
class PaywallScreen extends StatefulWidget {
  const PaywallScreen({super.key, this.onDismiss});

  /// Called when the user dismisses the paywall (optional)
  final VoidCallback? onDismiss;

  @override
  State<PaywallScreen> createState() => _PaywallScreenState();
}

class _PaywallScreenState extends State<PaywallScreen> {
  Offerings? _offerings;
  Package? _selectedPackage;
  bool _isLoading = true;
  bool _isPurchasing = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadOfferings();
  }

  Future<void> _loadOfferings() async {
    try {
      final offerings = await Purchases.getOfferings();
      if (offerings.current != null) {
        setState(() {
          _offerings = offerings;
          // Default to annual (best value)
          _selectedPackage = offerings.current!.annual ??
              offerings.current!.monthly ??
              offerings.current!.availablePackages.firstOrNull;
          _isLoading = false;
        });
      } else {
        setState(() {
          _errorMessage = 'No subscription plans available at this time.';
          _isLoading = false;
        });
      }
    } catch (e) {
      log('RevenueCat error: $e');
      setState(() {
        _errorMessage = 'Unable to load subscription options. Please try again.';
        _isLoading = false;
      });
    }
  }

  Future<void> _purchase() async {
    if (_selectedPackage == null || _isPurchasing) return;

    setState(() => _isPurchasing = true);
    try {
      final customerInfo = await Purchases.purchasePackage(_selectedPackage!);
      if (customerInfo.entitlements.active.containsKey('premium')) {
        if (mounted) {
          Navigator.of(context).pop(true); // signal success
        }
      }
    } on PurchasesErrorCode catch (e) {
      if (e != PurchasesErrorCode.purchaseCancelledError) {
        setState(() => _errorMessage = 'Purchase failed: ${e.name}');
      }
    } finally {
      if (mounted) setState(() => _isPurchasing = false);
    }
  }

  Future<void> _restorePurchases() async {
    setState(() => _isPurchasing = true);
    try {
      final customerInfo = await Purchases.restorePurchases();
      if (customerInfo.entitlements.active.containsKey('premium')) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Premium access restored!')),
          );
          Navigator.of(context).pop(true);
        }
      } else {
        setState(() => _errorMessage = 'No previous purchases found.');
      }
    } catch (e) {
      setState(() => _errorMessage = 'Restore failed. Please try again.');
    } finally {
      if (mounted) setState(() => _isPurchasing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.primary,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.close, color: Colors.white),
          onPressed: () {
            widget.onDismiss?.call();
            Navigator.of(context).pop(false);
          },
        ),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: Colors.white))
          : _buildContent(),
    );
  }

  Widget _buildContent() {
    final packages =
        _offerings?.current?.availablePackages ?? [];

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 0, 24, 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // Header
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: AppColors.secondary,
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.star_rounded,
              color: AppColors.primary,
              size: 40,
            ),
          ),
          const SizedBox(height: 24),
          const Text(
            'MigrateAU Premium',
            style: TextStyle(
              fontFamily: 'Inter',
              fontSize: 26,
              fontWeight: FontWeight.w700,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Get real-time alerts and unlock your full migration toolkit',
            style: TextStyle(
              fontFamily: 'Inter',
              fontSize: 15,
              color: Colors.white.withOpacity(0.8),
              height: 1.5,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),

          // Features list
          _buildFeaturesList(),
          const SizedBox(height: 32),

          // Package selector
          if (packages.isNotEmpty) ...[
            ...packages.map((pkg) => _buildPackageTile(pkg)),
            const SizedBox(height: 24),
          ],

          // Error message
          if (_errorMessage != null) ...[
            Text(
              _errorMessage!,
              style: const TextStyle(color: Colors.redAccent, fontSize: 13),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
          ],

          // CTA Button
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _isPurchasing ? null : _purchase,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.secondary,
                foregroundColor: AppColors.primary,
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              child: _isPurchasing
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: AppColors.primary,
                      ),
                    )
                  : Text(
                      _selectedPackage != null
                          ? 'Start for ${_selectedPackage!.storeProduct.priceString}'
                          : 'Subscribe Now',
                      style: const TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
            ),
          ),
          const SizedBox(height: 16),

          // Restore
          TextButton(
            onPressed: _isPurchasing ? null : _restorePurchases,
            child: const Text(
              'Restore Purchases',
              style: TextStyle(
                color: Colors.white70,
                fontSize: 13,
                decoration: TextDecoration.underline,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Cancel anytime. Subscription auto-renews unless cancelled '
            'at least 24 hours before the end of the current period.',
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 11,
              height: 1.5,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildFeaturesList() {
    final features = [
      (Icons.notifications_active, 'Real-time occupation & state alerts'),
      (Icons.track_changes, 'Detailed occupation tracking & history'),
      (Icons.smart_toy, 'Unlimited AI immigration consultant'),
      (Icons.bar_chart, 'SkillSelect round analytics & trends'),
      (Icons.bookmark, 'Save & compare multiple profiles'),
    ];

    return Column(
      children: features
          .map(
            (f) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(
                      color: AppColors.secondary.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(f.$1, color: AppColors.secondary, size: 20),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Text(
                      f.$2,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontFamily: 'Inter',
                      ),
                    ),
                  ),
                ],
              ),
            ),
          )
          .toList(),
    );
  }

  Widget _buildPackageTile(Package package) {
    final isSelected = _selectedPackage?.identifier == package.identifier;
    final isAnnual = package.packageType == PackageType.annual;

    return GestureDetector(
      onTap: () => setState(() => _selectedPackage = package),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isSelected
              ? Colors.white.withOpacity(0.15)
              : Colors.white.withOpacity(0.05),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? AppColors.secondary : Colors.white24,
            width: isSelected ? 2 : 1,
          ),
        ),
        child: Row(
          children: [
            Icon(
              isSelected ? Icons.radio_button_checked : Icons.radio_button_off,
              color: isSelected ? AppColors.secondary : Colors.white54,
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    package.storeProduct.title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontFamily: 'Inter',
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                  if (isAnnual)
                    const Text(
                      'Best Value — Save over 40%',
                      style: TextStyle(
                        color: AppColors.secondary,
                        fontSize: 11,
                        fontFamily: 'Inter',
                      ),
                    ),
                ],
              ),
            ),
            Text(
              package.storeProduct.priceString,
              style: const TextStyle(
                color: Colors.white,
                fontFamily: 'Inter',
                fontWeight: FontWeight.w700,
                fontSize: 16,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
