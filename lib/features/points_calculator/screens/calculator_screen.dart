import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../core/theme/app_theme.dart';
import '../cubit/calculator_cubit.dart';
import '../services/points_calculator_service.dart';

class CalculatorScreen extends StatelessWidget {
  const CalculatorScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Points Calculator')),
      body: BlocBuilder<CalculatorCubit, CalculatorState>(
        builder: (context, state) {
          final cubit = context.read<CalculatorCubit>();
          return Row(
            children: [
              // Left/Main column — scrollable form
              Expanded(
                flex: 3,
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    _VisaSubclassSelector(
                      selected: state.visaSubclass,
                      onChanged: cubit.updateVisaSubclass,
                    ),
                    const SizedBox(height: 20),
                    _FormSection(
                      title: 'Age',
                      child: _AgePicker(
                        age: state.age,
                        onChanged: cubit.updateAge,
                      ),
                    ),
                    _FormSection(
                      title: 'English Proficiency',
                      child: _EnglishSelector(
                        level: state.englishLevel,
                        onChanged: cubit.updateEnglish,
                      ),
                    ),
                    _FormSection(
                      title: 'Australian Work Experience',
                      child: _YearsPicker(
                        label: 'Years in Australia',
                        years: state.australianWorkYears,
                        onChanged: cubit.updateAustralianWork,
                      ),
                    ),
                    _FormSection(
                      title: 'Overseas Work Experience',
                      child: _YearsPicker(
                        label: 'Years overseas',
                        years: state.overseasWorkYears,
                        onChanged: cubit.updateOverseasWork,
                      ),
                    ),
                    _FormSection(
                      title: 'Bonus Points',
                      child: Column(
                        children: [
                          _SwitchTile(
                            label: 'Professional Year in Australia (+5)',
                            value: state.hasProfessionalYear,
                            onChanged: cubit.toggleProfessionalYear,
                          ),
                          _SwitchTile(
                            label: 'NAATI CCL (+5)',
                            value: state.hasNaati,
                            onChanged: cubit.toggleNaati,
                          ),
                          _SwitchTile(
                            label: 'Partner Skills Assessment (+5)',
                            value: state.hasPartnerSkills,
                            onChanged: cubit.togglePartnerSkills,
                          ),
                          if (state.hasPartnerSkills)
                            _SwitchTile(
                              label: '  ↳ Partner also has Superior English (+10 total)',
                              value: state.partnerSuperiorEnglish,
                              onChanged: cubit.togglePartnerSuperiorEnglish,
                            ),
                          _SwitchTile(
                            label: 'State/Territory Nomination',
                            value: state.hasStateNomination,
                            onChanged: cubit.toggleStateNomination,
                          ),
                          _SwitchTile(
                            label: 'Accredited Community Language (+5)',
                            value: state.hasCommunityLanguage,
                            onChanged: cubit.toggleCommunityLanguage,
                          ),
                          _SwitchTile(
                            label: 'Australian Study Requirement (+5)',
                            value: state.hasAustralianStudy,
                            onChanged: cubit.toggleAustralianStudy,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 32),
                  ],
                ),
              ),
              // Right column — Score summary (wider screens) or bottom on mobile
              if (MediaQuery.of(context).size.width > 700)
                SizedBox(
                  width: 260,
                  child: _ScoreSummaryPanel(state: state),
                ),
            ],
          );
        },
      ),
      bottomSheet:
          MediaQuery.of(context).size.width <= 700
              ? BlocBuilder<CalculatorCubit, CalculatorState>(
                  builder: (context, state) =>
                      _ScoreBottomBar(state: state),
                )
              : null,
    );
  }
}

// ---------------------------------------------------------------------------
// Visa Subclass Selector
// ---------------------------------------------------------------------------
class _VisaSubclassSelector extends StatelessWidget {
  const _VisaSubclassSelector({
    required this.selected,
    required this.onChanged,
  });

  final VisaSubclass selected;
  final ValueChanged<VisaSubclass> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Visa Subclass',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 15,
            color: AppColors.textPrimary,
          ),
        ),
        const SizedBox(height: 10),
        Row(
          children: VisaSubclass.values
              .map(
                (v) => Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: ChoiceChip(
                      label: Text(_subclassLabel(v)),
                      selected: selected == v,
                      onSelected: (_) => onChanged(v),
                      selectedColor: AppColors.primary,
                      labelStyle: TextStyle(
                        color: selected == v ? Colors.white : AppColors.textPrimary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              )
              .toList(),
        ),
      ],
    );
  }

  String _subclassLabel(VisaSubclass v) {
    switch (v) {
      case VisaSubclass.s189:
        return '189';
      case VisaSubclass.s190:
        return '190';
      case VisaSubclass.s491:
        return '491';
    }
  }
}

// ---------------------------------------------------------------------------
// Form Section wrapper
// ---------------------------------------------------------------------------
class _FormSection extends StatelessWidget {
  const _FormSection({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 14,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 12),
          child,
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Age Picker
// ---------------------------------------------------------------------------
class _AgePicker extends StatelessWidget {
  const _AgePicker({required this.age, required this.onChanged});

  final int age;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        IconButton(
          onPressed: age > 18 ? () => onChanged(age - 1) : null,
          icon: const Icon(Icons.remove_circle_outline),
          color: AppColors.primary,
        ),
        Expanded(
          child: Center(
            child: Text(
              '$age years',
              style: const TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: AppColors.primary,
              ),
            ),
          ),
        ),
        IconButton(
          onPressed: age < 49 ? () => onChanged(age + 1) : null,
          icon: const Icon(Icons.add_circle_outline),
          color: AppColors.primary,
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// English Selector
// ---------------------------------------------------------------------------
class _EnglishSelector extends StatelessWidget {
  const _EnglishSelector({required this.level, required this.onChanged});

  final EnglishLevel level;
  final ValueChanged<EnglishLevel> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: EnglishLevel.values
          .map(
            (e) => RadioListTile<EnglishLevel>(
              value: e,
              groupValue: level,
              onChanged: (v) => onChanged(v!),
              title: Text(_englishLabel(e)),
              subtitle: Text(_englishSubtitle(e)),
              dense: true,
              activeColor: AppColors.primary,
            ),
          )
          .toList(),
    );
  }

  String _englishLabel(EnglishLevel e) {
    switch (e) {
      case EnglishLevel.competent:
        return 'Competent English (+0)';
      case EnglishLevel.proficient:
        return 'Proficient English (+10)';
      case EnglishLevel.superior:
        return 'Superior English (+20)';
    }
  }

  String _englishSubtitle(EnglishLevel e) {
    switch (e) {
      case EnglishLevel.competent:
        return 'IELTS 6 / PTE 50';
      case EnglishLevel.proficient:
        return 'IELTS 7 / PTE 65';
      case EnglishLevel.superior:
        return 'IELTS 8 / PTE 79';
    }
  }
}

// ---------------------------------------------------------------------------
// Years Picker
// ---------------------------------------------------------------------------
class _YearsPicker extends StatelessWidget {
  const _YearsPicker({
    required this.label,
    required this.years,
    required this.onChanged,
  });

  final String label;
  final int years;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        IconButton(
          onPressed: years > 0 ? () => onChanged(years - 1) : null,
          icon: const Icon(Icons.remove_circle_outline),
          color: AppColors.primary,
        ),
        Expanded(
          child: Center(
            child: Text(
              '$years yr${years == 1 ? '' : 's'}',
              style: const TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: AppColors.primary,
              ),
            ),
          ),
        ),
        IconButton(
          onPressed: years < 20 ? () => onChanged(years + 1) : null,
          icon: const Icon(Icons.add_circle_outline),
          color: AppColors.primary,
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Switch Tile
// ---------------------------------------------------------------------------
class _SwitchTile extends StatelessWidget {
  const _SwitchTile({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return SwitchListTile.adaptive(
      title: Text(label, style: const TextStyle(fontSize: 13)),
      value: value,
      onChanged: onChanged,
      activeColor: AppColors.primary,
      dense: true,
    );
  }
}

// ---------------------------------------------------------------------------
// Score Summary Panel (wide screens)
// ---------------------------------------------------------------------------
class _ScoreSummaryPanel extends StatelessWidget {
  const _ScoreSummaryPanel({required this.state});

  final CalculatorState state;

  @override
  Widget build(BuildContext context) {
    final breakdown = state.breakdown;
    final total = breakdown?.total ?? 0;

    return Container(
      margin: const EdgeInsets.all(12),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withOpacity(0.06),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'Your Score',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.bold,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 12),
          Center(
            child: Text(
              '$total',
              style: TextStyle(
                fontSize: 64,
                fontWeight: FontWeight.bold,
                color: _scoreColor(total),
              ),
            ),
          ),
          Center(
            child: Text(
              breakdown != null
                  ? const PointsCalculatorService().scoreTierLabel(total)
                  : '—',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: _scoreColor(total),
              ),
            ),
          ),
          if (breakdown != null) ...[
            const Divider(height: 28),
            _BreakdownRow(label: 'Age', value: breakdown.age),
            _BreakdownRow(label: 'English', value: breakdown.english),
            _BreakdownRow(
                label: 'AU Work', value: breakdown.australianWork),
            _BreakdownRow(
                label: 'Overseas Work', value: breakdown.overseasWork),
            _BreakdownRow(
                label: 'Professional Year',
                value: breakdown.professionalYear),
            _BreakdownRow(label: 'NAATI', value: breakdown.naati),
            _BreakdownRow(label: 'Partner', value: breakdown.partner),
            _BreakdownRow(
                label: 'State Nomination',
                value: breakdown.stateNomination),
            _BreakdownRow(
                label: 'Community Lang.', value: breakdown.communityLanguage),
            _BreakdownRow(
                label: 'AU Study', value: breakdown.australianStudy),
            const Divider(height: 16),
            _BreakdownRow(
              label: 'TOTAL',
              value: breakdown.total,
              isBold: true,
            ),
          ],
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color:
                  (breakdown?.likelyEligible ?? false)
                      ? AppColors.success.withOpacity(0.1)
                      : AppColors.warning.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              (breakdown?.likelyEligible ?? false)
                  ? '✓ Likely eligible for an invitation'
                  : '⚠ Score may be below current round cutoffs',
              style: TextStyle(
                fontSize: 12,
                color: (breakdown?.likelyEligible ?? false)
                    ? AppColors.success
                    : AppColors.warning,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Color _scoreColor(int total) {
    if (total >= 70) return AppColors.scoreHigh;
    if (total >= 60) return AppColors.scoreMedium;
    return AppColors.scoreLow;
  }
}

class _BreakdownRow extends StatelessWidget {
  const _BreakdownRow({
    required this.label,
    required this.value,
    this.isBold = false,
  });

  final String label;
  final int value;
  final bool isBold;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: AppColors.textSecondary,
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
            ),
          ),
          Text(
            '+$value',
            style: TextStyle(
              fontSize: 12,
              color: isBold ? AppColors.primary : AppColors.textPrimary,
              fontWeight: isBold ? FontWeight.bold : FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Score Bottom Bar (narrow screens)
// ---------------------------------------------------------------------------
class _ScoreBottomBar extends StatelessWidget {
  const _ScoreBottomBar({required this.state});

  final CalculatorState state;

  @override
  Widget build(BuildContext context) {
    final total = state.breakdown?.total ?? 0;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      color: AppColors.primary,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text(
            'Your Points Score:',
            style: TextStyle(color: Colors.white70, fontSize: 13),
          ),
          Text(
            '$total pts',
            style: const TextStyle(
              color: AppColors.secondary,
              fontSize: 22,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }
}
