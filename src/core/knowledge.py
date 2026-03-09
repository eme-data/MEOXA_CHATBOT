"""Knowledge base per tenant - contextual search over site content."""

import json
import re
from pathlib import Path
from typing import Optional


class KnowledgeBase:
    """Stores and searches content entries for a tenant.

    Each entry represents a piece of site content (FAQ, page, product, etc.).
    Search uses TF-IDF-like keyword scoring to find relevant entries.
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.storage_path = Path(f"config/tenants/{tenant_id}/knowledge.json")
        self.entries: list[dict] = []
        self.load()

    def load(self) -> None:
        if self.storage_path.exists():
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self.entries = json.load(f)
        else:
            self.entries = []

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, indent=2)

    def add_entry(self, title: str, content: str, category: str = "general") -> dict:
        """Add a knowledge entry (FAQ, page content, product info, etc.)."""
        entry = {
            "id": len(self.entries),
            "title": title,
            "content": content,
            "category": category,
        }
        self.entries.append(entry)
        self._save()
        return entry

    def update_entry(self, entry_id: int, title: str, content: str, category: str = "general") -> dict:
        if entry_id < 0 or entry_id >= len(self.entries):
            raise IndexError(f"Entry {entry_id} not found")
        self.entries[entry_id] = {
            "id": entry_id,
            "title": title,
            "content": content,
            "category": category,
        }
        self._save()
        return self.entries[entry_id]

    def delete_entry(self, entry_id: int) -> None:
        if entry_id < 0 or entry_id >= len(self.entries):
            raise IndexError(f"Entry {entry_id} not found")
        self.entries.pop(entry_id)
        # Re-index
        for i, e in enumerate(self.entries):
            e["id"] = i
        self._save()

    def get_entries(self) -> list[dict]:
        return self.entries

    def search(self, query: str, max_results: int = 3) -> list[dict]:
        """Search knowledge base using keyword matching.

        Returns the most relevant entries based on word overlap scoring.
        """
        if not self.entries:
            return []

        query_words = self._tokenize(query)
        if not query_words:
            return []

        scored = []
        for entry in self.entries:
            # Combine title (weighted higher) and content for matching
            title_words = self._tokenize(entry["title"])
            content_words = self._tokenize(entry["content"])

            # Score: title matches worth 3x, content matches worth 1x
            score = 0
            for qw in query_words:
                for tw in title_words:
                    if qw in tw or tw in qw:
                        score += 3
                for cw in content_words:
                    if qw in cw or cw in qw:
                        score += 1

            if score > 0:
                scored.append((score, entry))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:max_results]]

    def build_context(self, query: str, max_results: int = 3) -> Optional[str]:
        """Build a context string from relevant knowledge entries.

        Returns None if no relevant content found.
        """
        results = self.search(query, max_results)
        if not results:
            return None

        context_parts = []
        for entry in results:
            context_parts.append(f"### {entry['title']}\n{entry['content']}")

        return "\n\n".join(context_parts)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple tokenization: lowercase, strip accents-ish, split on non-alpha."""
        text = text.lower()
        words = re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ]+", text)
        # Filter out very short words
        return [w for w in words if len(w) > 2]
