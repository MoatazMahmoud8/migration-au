import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import '../../../core/theme/app_theme.dart';
import '../cubit/ai_cubit.dart';
import '../services/ai_consultant_service.dart';

class AiAssistantScreen extends StatefulWidget {
  const AiAssistantScreen({super.key});

  @override
  State<AiAssistantScreen> createState() => _AiAssistantScreenState();
}

class _AiAssistantScreenState extends State<AiAssistantScreen> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _send(BuildContext context) {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    _controller.clear();
    context.read<AiCubit>().sendMessage(text);
    _scrollToBottom();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('AI Immigration Consultant'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Clear chat',
            onPressed: () => context.read<AiCubit>().clearChat(),
          ),
        ],
      ),
      body: Column(
        children: [
          // Aria header strip
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            color: AppColors.primary.withOpacity(0.05),
            child: Row(
              children: [
                CircleAvatar(
                  backgroundColor: AppColors.primary,
                  radius: 18,
                  child: const Text(
                    'A',
                    style: TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Aria — AI Immigration Consultant',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 13,
                          color: AppColors.primary,
                        ),
                      ),
                      Text(
                        'General information only. Consult a MARA agent for legal advice.',
                        style: TextStyle(
                          fontSize: 11,
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // Messages list
          Expanded(
            child: BlocConsumer<AiCubit, AiState>(
              listener: (context, state) => _scrollToBottom(),
              builder: (context, state) {
                if (state.messages.isEmpty) {
                  return const _WelcomePrompts();
                }
                return ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.all(12),
                  itemCount:
                      state.messages.length + (state.isLoading ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (index == state.messages.length && state.isLoading) {
                      return const _TypingIndicator();
                    }
                    final msg = state.messages[index];
                    return _MessageBubble(message: msg);
                  },
                );
              },
            ),
          ),

          // Error banner
          BlocBuilder<AiCubit, AiState>(
            builder: (context, state) {
              if (state.error == null) return const SizedBox.shrink();
              return Container(
                padding: const EdgeInsets.all(10),
                color: AppColors.error.withOpacity(0.1),
                child: Text(
                  state.error!,
                  style: const TextStyle(
                    color: AppColors.error,
                    fontSize: 12,
                  ),
                  textAlign: TextAlign.center,
                ),
              );
            },
          ),

          // Input bar
          const Divider(height: 1),
          Padding(
            padding: EdgeInsets.fromLTRB(
              12,
              8,
              12,
              8 + MediaQuery.of(context).viewInsets.bottom,
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    maxLines: 3,
                    minLines: 1,
                    decoration: InputDecoration(
                      hintText: 'Ask about your visa, points, or occupations…',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(24),
                        borderSide:
                            const BorderSide(color: AppColors.border),
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 10,
                      ),
                    ),
                    onSubmitted: (_) => _send(context),
                  ),
                ),
                const SizedBox(width: 8),
                BlocBuilder<AiCubit, AiState>(
                  builder: (context, state) => IconButton.filled(
                    onPressed: state.isLoading ? null : () => _send(context),
                    icon: state.isLoading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.send),
                    style: IconButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      foregroundColor: Colors.white,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Welcome prompts
// ---------------------------------------------------------------------------
class _WelcomePrompts extends StatelessWidget {
  const _WelcomePrompts();

  static const _suggestions = [
    'What is the points test and how does it work?',
    'How many points do I need for a 189 invitation?',
    'What states are currently open for 491 nominations?',
    'How does a Professional Year help my points?',
    'What is the NAATI CCL test?',
  ];

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const SizedBox(height: 20),
        const Center(
          child: Text(
            'Hi, I\'m Aria 👋',
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.bold,
              color: AppColors.primary,
            ),
          ),
        ),
        const SizedBox(height: 8),
        const Center(
          child: Text(
            'Ask me anything about Australian skilled migration.',
            style: TextStyle(
              fontSize: 14,
              color: AppColors.textSecondary,
            ),
            textAlign: TextAlign.center,
          ),
        ),
        const SizedBox(height: 28),
        const Text(
          'Suggested questions:',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 13,
            color: AppColors.textSecondary,
          ),
        ),
        const SizedBox(height: 12),
        ..._suggestions.map(
          (s) => _SuggestionChip(text: s),
        ),
      ],
    );
  }
}

class _SuggestionChip extends StatelessWidget {
  const _SuggestionChip({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: () => context.read<AiCubit>().sendMessage(text),
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            border: Border.all(color: AppColors.border),
            borderRadius: BorderRadius.circular(8),
            color: Colors.white,
          ),
          child: Row(
            children: [
              const Icon(Icons.chat_bubble_outline,
                  size: 16, color: AppColors.primary),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  text,
                  style: const TextStyle(
                    fontSize: 13,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
              const Icon(Icons.arrow_forward_ios,
                  size: 12, color: AppColors.textHint),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Message Bubble
// ---------------------------------------------------------------------------
class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final ChatMessage message;

  bool get isUser => message.role == 'user';

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.8,
        ),
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: isUser ? AppColors.primary : Colors.white,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isUser ? 16 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 16),
          ),
          border: isUser
              ? null
              : Border.all(color: AppColors.border),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.04),
              blurRadius: 6,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: isUser
            ? Text(
                message.text,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                ),
              )
            : MarkdownBody(
                data: message.text,
                styleSheet: MarkdownStyleSheet(
                  p: const TextStyle(
                    fontSize: 14,
                    color: AppColors.textPrimary,
                    height: 1.5,
                  ),
                  h3: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: AppColors.primary,
                  ),
                  listBullet: const TextStyle(
                    fontSize: 14,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Typing Indicator
// ---------------------------------------------------------------------------
class _TypingIndicator extends StatelessWidget {
  const _TypingIndicator();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(16),
            topRight: Radius.circular(16),
            bottomRight: Radius.circular(16),
            bottomLeft: Radius.circular(4),
          ),
          border: Border.all(color: AppColors.border),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 40,
              height: 16,
              child: _DotsIndicator(),
            ),
            SizedBox(width: 8),
            Text(
              'Aria is thinking…',
              style: TextStyle(
                fontSize: 12,
                color: AppColors.textHint,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DotsIndicator extends StatelessWidget {
  const _DotsIndicator();

  @override
  Widget build(BuildContext context) {
    return const Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: [
        _Dot(delay: Duration(milliseconds: 0)),
        _Dot(delay: Duration(milliseconds: 160)),
        _Dot(delay: Duration(milliseconds: 320)),
      ],
    );
  }
}

class _Dot extends StatefulWidget {
  const _Dot({required this.delay});

  final Duration delay;

  @override
  State<_Dot> createState() => _DotState();
}

class _DotState extends State<_Dot> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    Future.delayed(widget.delay, () {
      if (mounted) _ctrl.repeat(reverse: true);
    });
    _anim = Tween<double>(begin: 0.4, end: 1).animate(_ctrl);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _anim,
      child: const CircleAvatar(
        radius: 3,
        backgroundColor: AppColors.primary,
      ),
    );
  }
}
