part of 'profile_cubit.dart';

class ProfileState extends Equatable {
  final String name;
  final String anzscoCode;
  final bool isPremium;

  const ProfileState({
    this.name = '',
    this.anzscoCode = '',
    this.isPremium = false,
  });

  ProfileState copyWith({
    String? name,
    String? anzscoCode,
    bool? isPremium,
  }) =>
      ProfileState(
        name: name ?? this.name,
        anzscoCode: anzscoCode ?? this.anzscoCode,
        isPremium: isPremium ?? this.isPremium,
      );

  @override
  List<Object?> get props => [name, anzscoCode, isPremium];
}
