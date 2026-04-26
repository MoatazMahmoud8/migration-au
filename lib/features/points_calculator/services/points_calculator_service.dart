/// Visa subclass being calculated
enum VisaSubclass { s189, s190, s491 }

/// English proficiency level
enum EnglishLevel {
  competent, // IELTS 6 / PTE 50
  proficient, // IELTS 7 / PTE 65
  superior, // IELTS 8 / PTE 79
}

/// Input model for the points calculation
class PointsInput {
  final int age;
  final EnglishLevel englishLevel;
  final int australianWorkExperienceYears;
  final int overseasWorkExperienceYears;
  final bool hasProfessionalYear;
  final bool hasNaatiCcl;
  final bool hasPartnerSkills; // partner has skills assessment + competent English
  final bool partnerSuperiorEnglish; // partner also has superior English
  final bool hasStateNomination;
  final VisaSubclass visaSubclass;
  final bool hasAccreditedCommunityLanguage;
  final bool hasAustralianStudyRequirement;

  const PointsInput({
    required this.age,
    required this.englishLevel,
    required this.australianWorkExperienceYears,
    required this.overseasWorkExperienceYears,
    required this.visaSubclass,
    this.hasProfessionalYear = false,
    this.hasNaatiCcl = false,
    this.hasPartnerSkills = false,
    this.partnerSuperiorEnglish = false,
    this.hasStateNomination = false,
    this.hasAccreditedCommunityLanguage = false,
    this.hasAustralianStudyRequirement = false,
  });
}

/// Breakdown of each scoring category
class PointsBreakdown {
  final int age;
  final int english;
  final int australianWork;
  final int overseasWork;
  final int professionalYear;
  final int naati;
  final int partner;
  final int stateNomination;
  final int communityLanguage;
  final int australianStudy;

  const PointsBreakdown({
    required this.age,
    required this.english,
    required this.australianWork,
    required this.overseasWork,
    required this.professionalYear,
    required this.naati,
    required this.partner,
    required this.stateNomination,
    required this.communityLanguage,
    required this.australianStudy,
  });

  int get total =>
      age +
      english +
      australianWork +
      overseasWork +
      professionalYear +
      naati +
      partner +
      stateNomination +
      communityLanguage +
      australianStudy;

  /// Typical minimum to receive an invitation (indicative, varies by round)
  bool get likelyEligible => total >= 65;
}

/// Points Calculator Service
///
/// Implements the Department of Home Affairs SkillSelect points test.
/// Reference: https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189/points-tested
class PointsCalculatorService {
  const PointsCalculatorService();

  /// Calculate points and return a full breakdown
  PointsBreakdown calculate(PointsInput input) {
    return PointsBreakdown(
      age: _calculateAge(input.age),
      english: _calculateEnglish(input.englishLevel),
      australianWork:
          _calculateAustralianWork(input.australianWorkExperienceYears),
      overseasWork: _calculateOverseasWork(input.overseasWorkExperienceYears),
      professionalYear: input.hasProfessionalYear ? 5 : 0,
      naati: input.hasNaatiCcl ? 5 : 0,
      partner: _calculatePartner(
        hasPartnerSkills: input.hasPartnerSkills,
        partnerSuperiorEnglish: input.partnerSuperiorEnglish,
      ),
      stateNomination: _calculateStateNomination(
        hasNomination: input.hasStateNomination,
        subclass: input.visaSubclass,
      ),
      communityLanguage: input.hasAccreditedCommunityLanguage ? 5 : 0,
      australianStudy: input.hasAustralianStudyRequirement ? 5 : 0,
    );
  }

  // ---------------------------------------------------------------------------
  // Age Points — maximum 30
  // ---------------------------------------------------------------------------
  int _calculateAge(int age) {
    if (age >= 18 && age <= 24) return 25;
    if (age >= 25 && age <= 32) return 30;
    if (age >= 33 && age <= 39) return 25;
    if (age >= 40 && age <= 44) return 15;
    if (age >= 45 && age <= 49) return 0;
    // Under 18 or 50+ are not eligible for the points test
    return 0;
  }

  // ---------------------------------------------------------------------------
  // English Proficiency Points — maximum 20
  // ---------------------------------------------------------------------------
  int _calculateEnglish(EnglishLevel level) {
    switch (level) {
      case EnglishLevel.competent:
        return 0; // Minimum requirement but no bonus points
      case EnglishLevel.proficient:
        return 10;
      case EnglishLevel.superior:
        return 20;
    }
  }

  // ---------------------------------------------------------------------------
  // Australian Skilled Work Experience — maximum 20
  // Requires: in nominated occupation, on a skilled visa (or citizen/PR)
  // ---------------------------------------------------------------------------
  int _calculateAustralianWork(int years) {
    if (years >= 8) return 20;
    if (years >= 5) return 15;
    if (years >= 3) return 10;
    if (years >= 1) return 5;
    return 0;
  }

  // ---------------------------------------------------------------------------
  // Overseas Skilled Work Experience — maximum 15
  // ---------------------------------------------------------------------------
  int _calculateOverseasWork(int years) {
    if (years >= 8) return 15;
    if (years >= 5) return 10;
    if (years >= 3) return 5;
    return 0;
  }

  // ---------------------------------------------------------------------------
  // Partner Points — maximum 10
  // ---------------------------------------------------------------------------
  int _calculatePartner({
    required bool hasPartnerSkills,
    required bool partnerSuperiorEnglish,
  }) {
    if (hasPartnerSkills && partnerSuperiorEnglish) return 10;
    if (hasPartnerSkills) return 5;
    return 0;
  }

  // ---------------------------------------------------------------------------
  // State / Territory Nomination
  // 190 = 5 pts | 491 = 15 pts | 189 = 0 (no nomination)
  // ---------------------------------------------------------------------------
  int _calculateStateNomination({
    required bool hasNomination,
    required VisaSubclass subclass,
  }) {
    if (!hasNomination) return 0;
    switch (subclass) {
      case VisaSubclass.s190:
        return 5;
      case VisaSubclass.s491:
        return 15;
      case VisaSubclass.s189:
        return 0; // 189 doesn't require nomination
    }
  }

  // ---------------------------------------------------------------------------
  // Helper: Human-readable score tier label
  // ---------------------------------------------------------------------------
  String scoreTierLabel(int total) {
    if (total >= 90) return 'Exceptional';
    if (total >= 80) return 'Excellent';
    if (total >= 70) return 'Strong';
    if (total >= 65) return 'Competitive';
    if (total >= 60) return 'Moderate';
    return 'Below Threshold';
  }
}
