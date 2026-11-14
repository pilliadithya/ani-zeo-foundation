# Multilingual Anime NLU

## Purpose

The intent gate runs before the AI response writer. It must not reject short follow-up
messages merely because the user omitted the anime or character name. The detector
uses recent conversation context to decide whether an otherwise ambiguous message
continues an anime/manga topic.

## Current implementation

- Deterministic, anime-domain-aware intent and scope classification.
- English pronouns and common Romanized Telugu reference forms.
- Common Telugu-script pronouns and follow-up terms.
- Follow-up context is limited to recent messages and known anime/franchise/character
  vocabulary.
- Explicit unrelated requests remain out of scope.
- No external API, paid service, model download, or additional runtime dependency.

## Example

Conversation:
- User: "Luffy ki father evaru?"
- Ani Zeo: "Luffy ki father Monkey D Dragon..."
- User: "Konchem anthani power cheppa galava?"

Expected route:
- scope: anime
- intent: character_question
- is_follow_up: true

The response writer already receives the recent conversation history, so the resolved
subject remains available to the model. The detector's job is to prevent the scope gate
from redirecting the message before that context can be used.

## Next research stage

This deterministic layer is a low-latency safety net, not a claim of complete Telugu
NLU. Evaluate a labeled Telugu-script, Romanized Telugu, English, and code-mixed
dataset before considering a trained classifier. Candidate research baselines include
Rasa DIET, AI4Bharat IndicBERT (Telugu-script coverage), and multilingual embedding
models such as BGE-M3. Romanized Telugu spelling variation requires dedicated examples
and evaluation; model language coverage alone does not establish transliteration quality.
