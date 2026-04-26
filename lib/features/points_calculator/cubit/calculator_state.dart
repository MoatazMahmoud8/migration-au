part of 'calculator_cubit.dart';

class CalculatorState extends Equatable {
  final int age;
  final EnglishLevel englishLevel;
  final int australianWorkYears;
  final int overseasWorkYears;
  final VisaSubclass visaSubclass;
  final bool hasProfessionalYear;
  final bool hasNaati;
  final bool hasPartnerSkills;
  final bool partnerSuperiorEnglish;
  final bool hasStateNomination;
  final bool hasCommunityLanguage;
  final bool hasAustralianStudy;
  final PointsBreakdown? breakdown;

  const CalculatorState({
    this.age = 30,
    this.englishLevel = EnglishLevel.proficient,
    this.australianWorkYears = 0,
    this.overseasWorkYears = 3,
    this.visaSubclass = VisaSubclass.s189,
    this.hasProfessionalYear = false,
    this.hasNaati = false,
    this.hasPartnerSkills = false,
    this.partnerSuperiorEnglish = false,
    this.hasStateNomination = false,
    this.hasCommunityLanguage = false,
    this.hasAustralianStudy = false,
    this.breakdown,
  });

  CalculatorState copyWith({
    int? age,
    EnglishLevel? englishLevel,
    int? australianWorkYears,
    int? overseasWorkYears,
    VisaSubclass? visaSubclass,
    bool? hasProfessionalYear,
    bool? hasNaati,
    bool? hasPartnerSkills,
    bool? partnerSuperiorEnglish,
    bool? hasStateNomination,
    bool? hasCommunityLanguage,
    bool? hasAustralianStudy,
    PointsBreakdown? breakdown,
  }) =>
      CalculatorState(
        age: age ?? this.age,
        englishLevel: englishLevel ?? this.englishLevel,
        australianWorkYears: australianWorkYears ?? this.australianWorkYears,
        overseasWorkYears: overseasWorkYears ?? this.overseasWorkYears,
        visaSubclass: visaSubclass ?? this.visaSubclass,
        hasProfessionalYear: hasProfessionalYear ?? this.hasProfessionalYear,
        hasNaati: hasNaati ?? this.hasNaati,
        hasPartnerSkills: hasPartnerSkills ?? this.hasPartnerSkills,
        partnerSuperiorEnglish:
            partnerSuperiorEnglish ?? this.partnerSuperiorEnglish,
        hasStateNomination: hasStateNomination ?? this.hasStateNomination,
        hasCommunityLanguage: hasCommunityLanguage ?? this.hasCommunityLanguage,
        hasAustralianStudy: hasAustralianStudy ?? this.hasAustralianStudy,
        breakdown: breakdown ?? this.breakdown,
      );

  @override
  List<Object?> get props => [
        age,
        englishLevel,
        australianWorkYears,
        overseasWorkYears,
        visaSubclass,
        hasProfessionalYear,
        hasNaati,
        hasPartnerSkills,
        partnerSuperiorEnglish,
        hasStateNomination,
        hasCommunityLanguage,
        hasAustralianStudy,
        breakdown,
      ];
}
