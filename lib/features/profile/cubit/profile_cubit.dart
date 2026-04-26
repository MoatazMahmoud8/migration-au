import 'package:equatable/equatable.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:shared_preferences/shared_preferences.dart';

part 'profile_state.dart';

class ProfileCubit extends Cubit<ProfileState> {
  ProfileCubit() : super(const ProfileState());

  static const _keyName = 'profile_name';
  static const _keyAnzsco = 'profile_anzsco';
  static const _keyIsPremium = 'profile_is_premium';

  Future<void> loadProfile() async {
    final prefs = await SharedPreferences.getInstance();
    emit(state.copyWith(
      name: prefs.getString(_keyName) ?? '',
      anzscoCode: prefs.getString(_keyAnzsco) ?? '',
      isPremium: prefs.getBool(_keyIsPremium) ?? false,
    ));
  }

  Future<void> updateName(String name) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyName, name);
    emit(state.copyWith(name: name));
  }

  Future<void> updateAnzsco(String code) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyAnzsco, code);
    emit(state.copyWith(anzscoCode: code));
  }

  Future<void> setPremium(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyIsPremium, value);
    emit(state.copyWith(isPremium: value));
  }
}
