import 'package:equatable/equatable.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../services/points_calculator_service.dart';

part 'calculator_state.dart';

class CalculatorCubit extends Cubit<CalculatorState> {
  CalculatorCubit() : super(const CalculatorState());

  final _service = const PointsCalculatorService();

  void updateAge(int age) {
    emit(state.copyWith(age: age));
    _recalculate();
  }

  void updateEnglish(EnglishLevel level) {
    emit(state.copyWith(englishLevel: level));
    _recalculate();
  }

  void updateAustralianWork(int years) {
    emit(state.copyWith(australianWorkYears: years));
    _recalculate();
  }

  void updateOverseasWork(int years) {
    emit(state.copyWith(overseasWorkYears: years));
    _recalculate();
  }

  void updateVisaSubclass(VisaSubclass subclass) {
    emit(state.copyWith(visaSubclass: subclass));
    _recalculate();
  }

  void toggleProfessionalYear(bool value) {
    emit(state.copyWith(hasProfessionalYear: value));
    _recalculate();
  }

  void toggleNaati(bool value) {
    emit(state.copyWith(hasNaati: value));
    _recalculate();
  }

  void togglePartnerSkills(bool value) {
    emit(state.copyWith(hasPartnerSkills: value));
    _recalculate();
  }

  void togglePartnerSuperiorEnglish(bool value) {
    emit(state.copyWith(partnerSuperiorEnglish: value));
    _recalculate();
  }

  void toggleStateNomination(bool value) {
    emit(state.copyWith(hasStateNomination: value));
    _recalculate();
  }

  void toggleCommunityLanguage(bool value) {
    emit(state.copyWith(hasCommunityLanguage: value));
    _recalculate();
  }

  void toggleAustralianStudy(bool value) {
    emit(state.copyWith(hasAustralianStudy: value));
    _recalculate();
  }

  void _recalculate() {
    final input = PointsInput(
      age: state.age,
      englishLevel: state.englishLevel,
      australianWorkExperienceYears: state.australianWorkYears,
      overseasWorkExperienceYears: state.overseasWorkYears,
      visaSubclass: state.visaSubclass,
      hasProfessionalYear: state.hasProfessionalYear,
      hasNaatiCcl: state.hasNaati,
      hasPartnerSkills: state.hasPartnerSkills,
      partnerSuperiorEnglish: state.partnerSuperiorEnglish,
      hasStateNomination: state.hasStateNomination,
      hasAccreditedCommunityLanguage: state.hasCommunityLanguage,
      hasAustralianStudyRequirement: state.hasAustralianStudy,
    );

    final breakdown = _service.calculate(input);
    emit(state.copyWith(breakdown: breakdown));
  }
}
