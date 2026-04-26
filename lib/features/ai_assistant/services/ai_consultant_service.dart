import 'dart:developer';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:google_generative_ai/google_generative_ai.dart';

/// A message in the conversation history
class ChatMessage {
  final String role; // 'user' | 'model'
  final String text;
  final DateTime timestamp;

  const ChatMessage({
    required this.role,
    required this.text,
    required this.timestamp,
  });
}

/// AI Immigration Consultant Service
///
/// Uses Google Gemini API configured as an Australian immigration consultant.
/// Fetches recent news/updates from Firestore to provide context-aware answers.
class AiConsultantService {
  AiConsultantService({required String apiKey})
      : _model = GenerativeModel(
          model: 'gemini-1.5-pro',
          apiKey: apiKey,
          systemInstruction: Content.system(_systemPrompt),
          generationConfig: GenerationConfig(
            temperature: 0.4,
            topP: 0.95,
            maxOutputTokens: 1024,
          ),
          safetySettings: [
            SafetySetting(
              HarmCategory.harassment,
              HarmBlockThreshold.medium,
            ),
            SafetySetting(
              HarmCategory.dangerousContent,
              HarmBlockThreshold.medium,
            ),
          ],
        );

  final GenerativeModel _model;
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  ChatSession? _session;

  // ---------------------------------------------------------------------------
  // System Prompt
  // ---------------------------------------------------------------------------
  static const String _systemPrompt = '''
You are an expert Australian immigration consultant named "Aria". 
You specialise in the General Skilled Migration (GSM) program, including:
- Subclass 189 (Skilled Independent)
- Subclass 190 (Skilled Nominated)
- Subclass 491 (Skilled Work Regional)

Your responsibilities:
1. Calculate and explain points test eligibility.
2. Explain state/territory nomination requirements and current openings.
3. Explain occupation assessment processes for different assessing authorities (ACS, Engineers Australia, VETASSESS, etc.).
4. Interpret the latest SkillSelect invitation rounds and trends.
5. Answer questions about English language requirements (IELTS, PTE, OET, TOEFL).
6. Explain the ANZSCO occupation classification system.

Rules:
- Always provide accurate, up-to-date information based on the context provided.
- When in doubt, advise the user to consult a Registered Migration Agent (MARA).
- Never provide legal advice. Clarify you provide general information only.
- Be concise, professional, and empathetic — many users are anxious about their visa journey.
- Use Australian spelling (e.g. "programme", "organised").
- Format responses with clear headings and bullet points where helpful.
''';

  // ---------------------------------------------------------------------------
  // Initialize / reset conversation
  // ---------------------------------------------------------------------------

  Future<void> startNewSession() async {
    final contextContent = await _buildContextContent();
    _session = _model.startChat(
      history: contextContent.isNotEmpty
          ? [Content.model([TextPart(contextContent)])]
          : [],
    );
    log('AiConsultantService: new session started with context');
  }

  // ---------------------------------------------------------------------------
  // Send message
  // ---------------------------------------------------------------------------

  /// Send a user message and return the model's response text.
  Future<String> sendMessage(String userMessage) async {
    if (_session == null) {
      await startNewSession();
    }

    try {
      final response = await _session!.sendMessage(
        Content.text(userMessage),
      );
      return response.text ?? 'Sorry, I could not generate a response.';
    } on GenerativeAIException catch (e) {
      log('Gemini error: $e');
      return 'I encountered an error processing your request. Please try again.';
    } catch (e) {
      log('AiConsultantService error: $e');
      return 'An unexpected error occurred. Please try again later.';
    }
  }

  // ---------------------------------------------------------------------------
  // Context builder — fetches recent news from Firestore
  // ---------------------------------------------------------------------------

  Future<String> _buildContextContent() async {
    try {
      final snapshot = await _firestore
          .collection('news')
          .orderBy('publishedAt', descending: true)
          .limit(5)
          .get();

      if (snapshot.docs.isEmpty) return '';

      final buffer = StringBuffer();
      buffer.writeln('=== RECENT AUSTRALIAN MIGRATION NEWS (last updated) ===');

      for (final doc in snapshot.docs) {
        final data = doc.data();
        buffer.writeln('---');
        buffer.writeln('Title: ${data['title'] ?? 'Untitled'}');
        buffer.writeln('State: ${data['state'] ?? 'National'}');
        buffer.writeln('Summary: ${data['summary'] ?? ''}');
        if (data['publishedAt'] != null) {
          final ts = (data['publishedAt'] as Timestamp).toDate();
          buffer.writeln('Published: $ts');
        }
      }

      buffer.writeln('=== END OF CONTEXT ===');
      buffer.writeln(
        'Use the above news to inform your answers. '
        'If directly relevant, cite the article in your response.',
      );

      return buffer.toString();
    } catch (e) {
      log('Failed to fetch context from Firestore: $e');
      return '';
    }
  }
}
