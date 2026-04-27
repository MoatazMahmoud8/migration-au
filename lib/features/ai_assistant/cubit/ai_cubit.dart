import 'package:equatable/equatable.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../core/config/app_config.dart';
import '../services/ai_consultant_service.dart';

part 'ai_state.dart';

class AiCubit extends Cubit<AiState> {
  AiCubit() : super(const AiState());

  final _service = AiConsultantService(apiKey: AppConfig.geminiApiKey);

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
