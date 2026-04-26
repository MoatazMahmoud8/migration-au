part of 'ai_cubit.dart';

class AiState extends Equatable {
  final List<ChatMessage> messages;
  final bool isLoading;
  final String? error;

  const AiState({
    this.messages = const [],
    this.isLoading = false,
    this.error,
  });

  AiState copyWith({
    List<ChatMessage>? messages,
    bool? isLoading,
    String? error,
  }) =>
      AiState(
        messages: messages ?? this.messages,
        isLoading: isLoading ?? this.isLoading,
        error: error,
      );

  @override
  List<Object?> get props => [messages, isLoading, error];
}
