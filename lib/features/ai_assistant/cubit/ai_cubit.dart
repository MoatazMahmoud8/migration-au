import 'package:equatable/equatable.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../services/ai_consultant_service.dart';

part 'ai_state.dart';

class AiCubit extends Cubit<AiState> {
  AiCubit() : super(const AiState());

  // Replace with your actual Gemini API key or load from env/config
  final _service = AiConsultantService(
    apiKey: const String.fromEnvironment(
      'GEMINI_API_KEY',
      defaultValue: 'YOUR_GEMINI_API_KEY',
    ),
  );

  Future<void> sendMessage(String text) async {
    if (text.trim().isEmpty) return;

    final userMsg = ChatMessage(
      role: 'user',
      text: text.trim(),
      timestamp: DateTime.now(),
    );

    emit(
      state.copyWith(
        messages: [...state.messages, userMsg],
        isLoading: true,
        error: null,
      ),
    );

    try {
      final response = await _service.sendMessage(text.trim());

      final modelMsg = ChatMessage(
        role: 'model',
        text: response,
        timestamp: DateTime.now(),
      );

      emit(
        state.copyWith(
          messages: [...state.messages, modelMsg],
          isLoading: false,
        ),
      );
    } catch (e) {
      emit(
        state.copyWith(
          isLoading: false,
          error: 'Failed to get a response. Please try again.',
        ),
      );
    }
  }

  void clearChat() {
    emit(const AiState());
    _service.startNewSession();
  }
}
