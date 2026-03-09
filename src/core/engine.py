"""Main chatbot engine - orchestrates scripted and AI responses."""

import logging
from typing import Optional

from src.core.scripted import ScriptedResponder
from src.core.claude_provider import ClaudeProvider
from src.core.knowledge import KnowledgeBase

logger = logging.getLogger(__name__)


class ChatEngine:
    """Central engine that routes messages through scripted rules,
    then knowledge base search, then optionally Claude API
    (constrained to site context)."""

    def __init__(
        self,
        tenant_id: str,
        responses_path: str = "config/responses.json",
        claude_api_key: Optional[str] = None,
        claude_model: str = "claude-sonnet-4-20250514",
        system_prompt: str = "Tu es un assistant utile et professionnel.",
    ):
        self.tenant_id = tenant_id
        self.scripted = ScriptedResponder(responses_path)
        self.knowledge = KnowledgeBase(tenant_id)
        self.claude: Optional[ClaudeProvider] = None
        self.system_prompt = system_prompt

        if claude_api_key:
            self.claude = ClaudeProvider(
                api_key=claude_api_key,
                model=claude_model,
                system_prompt=system_prompt,
            )
            logger.info("Claude API provider enabled (model: %s)", claude_model)
        else:
            logger.info("Running in scripted-only mode (no Claude API key)")

    async def handle_message(self, user_message: str, user_id: str = "") -> str:
        """Process an incoming message and return a response.

        1. Try scripted rules first
        2. Search knowledge base for relevant content
        3. If Claude is configured, use it WITH knowledge context (stays on-topic)
        4. If knowledge found but no Claude, return knowledge excerpt
        5. Otherwise return default response
        """
        # 1. Scripted match (exact patterns)
        scripted_response = self.scripted.match(user_message)
        if scripted_response:
            logger.debug("Scripted match for user %s", user_id)
            return scripted_response

        # 2. Search knowledge base
        knowledge_context = self.knowledge.build_context(user_message)

        # 3. Claude API with knowledge context (constrained to site content)
        if self.claude:
            logger.debug("Using Claude API for user %s", user_id)
            try:
                return await self.claude.get_response(
                    user_message, user_id, knowledge_context
                )
            except Exception as e:
                logger.error("Claude API error: %s", e)
                # Fall through to knowledge-only response

        # 4. Knowledge-only response (no Claude)
        if knowledge_context:
            results = self.knowledge.search(user_message, max_results=1)
            if results:
                return f"{results[0]['title']}\n\n{results[0]['content']}"

        # 5. Default
        return self.scripted.default_response
