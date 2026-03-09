"""Claude API provider - optional AI-powered responses."""

import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)


class ClaudeProvider:
    """Handles communication with the Claude API for AI responses."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        system_prompt: str = "Tu es un assistant utile et professionnel.",
        max_tokens: int = 1024,
    ):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        # Simple in-memory conversation history per user
        self._histories: dict[str, list[dict]] = {}
        self._max_history = 10  # Keep last N messages per user

    async def get_response(
        self,
        user_message: str,
        user_id: str = "",
        knowledge_context: str | None = None,
    ) -> str:
        """Get a response from Claude API, constrained to site context.

        If knowledge_context is provided, Claude is instructed to ONLY
        answer based on that content. This prevents the LLM from going
        off-topic or hallucinating outside the client's site content.
        """
        # Build system prompt with context constraint
        if knowledge_context:
            system = (
                f"{self.system_prompt}\n\n"
                "IMPORTANT: Tu dois UNIQUEMENT répondre en te basant sur le contenu "
                "ci-dessous. Si la question ne concerne pas ce contenu, réponds poliment "
                "que tu ne peux répondre qu'aux questions liées à ce site.\n\n"
                f"--- CONTENU DU SITE ---\n{knowledge_context}\n--- FIN DU CONTENU ---"
            )
        else:
            system = (
                f"{self.system_prompt}\n\n"
                "IMPORTANT: Aucun contenu de référence n'est disponible pour cette question. "
                "Réponds poliment que tu ne disposes pas d'informations suffisantes "
                "et invite l'utilisateur à reformuler ou contacter le support."
            )

        # Build conversation history
        history = self._histories.get(user_id, [])
        history.append({"role": "user", "content": user_message})

        # Trim history if too long
        if len(history) > self._max_history * 2:
            history = history[-self._max_history * 2:]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=history,
        )

        assistant_message = response.content[0].text

        # Save to history
        history.append({"role": "assistant", "content": assistant_message})
        self._histories[user_id] = history

        return assistant_message

    def clear_history(self, user_id: str) -> None:
        """Clear conversation history for a user."""
        self._histories.pop(user_id, None)

    def clear_all_histories(self) -> None:
        """Clear all conversation histories."""
        self._histories.clear()
