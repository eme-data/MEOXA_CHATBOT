"""Scripted response handler - pattern matching based responses."""

import json
import re
from pathlib import Path
from typing import Optional


class ScriptedResponder:
    """Handles scripted responses based on keyword/pattern matching."""

    def __init__(self, responses_path: str = "config/responses.json"):
        self.responses_path = Path(responses_path)
        self.rules: list[dict] = []
        self.default_response: str = "Désolé, je n'ai pas compris votre demande. Pouvez-vous reformuler ?"
        self.load()

    def load(self) -> None:
        """Load response rules from JSON config file."""
        if not self.responses_path.exists():
            self.rules = []
            return
        with open(self.responses_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.rules = data.get("rules", [])
        self.default_response = data.get("default_response", self.default_response)

    def reload(self) -> None:
        """Reload rules from disk (useful after API updates)."""
        self.load()

    def match(self, user_message: str) -> Optional[str]:
        """Try to match user message against scripted rules.

        Returns the response string if matched, None otherwise.
        """
        text = user_message.lower().strip()
        for rule in self.rules:
            patterns = rule.get("patterns", [])
            for pattern in patterns:
                if re.search(pattern.lower(), text):
                    return rule["response"]
        return None

    def get_rules(self) -> list[dict]:
        """Return all current rules."""
        return self.rules

    def add_rule(self, patterns: list[str], response: str) -> dict:
        """Add a new scripted rule."""
        rule = {"patterns": patterns, "response": response}
        self.rules.append(rule)
        self._save()
        return rule

    def update_rule(self, index: int, patterns: list[str], response: str) -> dict:
        """Update an existing rule by index."""
        if index < 0 or index >= len(self.rules):
            raise IndexError(f"Rule index {index} out of range")
        self.rules[index] = {"patterns": patterns, "response": response}
        self._save()
        return self.rules[index]

    def delete_rule(self, index: int) -> None:
        """Delete a rule by index."""
        if index < 0 or index >= len(self.rules):
            raise IndexError(f"Rule index {index} out of range")
        self.rules.pop(index)
        self._save()

    def _save(self) -> None:
        """Persist rules to JSON file."""
        self.responses_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"default_response": self.default_response, "rules": self.rules}
        with open(self.responses_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
