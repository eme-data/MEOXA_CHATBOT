"""Multi-tenant management - each client gets isolated configuration."""

import json
import logging
from pathlib import Path
from typing import Optional

from src.core.engine import ChatEngine

logger = logging.getLogger(__name__)


class Tenant:
    """Represents a single client/tenant with its own chatbot config."""

    def __init__(self, tenant_id: str, config: dict):
        self.tenant_id = tenant_id
        self.name: str = config.get("name", tenant_id)
        self.telegram_token: Optional[str] = config.get("telegram_token")
        self.claude_api_key: Optional[str] = config.get("claude_api_key")
        self.claude_model: str = config.get("claude_model", "claude-sonnet-4-20250514")
        self.system_prompt: str = config.get(
            "system_prompt", "Tu es un assistant utile et professionnel."
        )
        self.enabled: bool = config.get("enabled", True)

        # Each tenant gets its own response file and engine
        self.responses_path = f"config/tenants/{tenant_id}/responses.json"
        self._ensure_config()
        self.engine = ChatEngine(
            tenant_id=tenant_id,
            responses_path=self.responses_path,
            claude_api_key=self.claude_api_key,
            claude_model=self.claude_model,
            system_prompt=self.system_prompt,
        )

    def _ensure_config(self) -> None:
        """Ensure tenant config directory and default responses exist."""
        path = Path(self.responses_path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Copy default responses
            default = Path("config/responses.json")
            if default.exists():
                import shutil
                shutil.copy(default, path)
            else:
                data = {"default_response": "Désolé, je n'ai pas compris.", "rules": []}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

    def to_dict(self) -> dict:
        """Serialize tenant info (without secrets)."""
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "enabled": self.enabled,
            "has_telegram": bool(self.telegram_token),
            "has_claude": bool(self.claude_api_key),
            "claude_model": self.claude_model,
        }


class TenantManager:
    """Manages all tenants from a central config file."""

    CONFIG_PATH = Path("config/tenants.json")

    def __init__(self):
        self.tenants: dict[str, Tenant] = {}
        self.load()

    def load(self) -> None:
        """Load all tenants from config."""
        if not self.CONFIG_PATH.exists():
            self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._save_config({})
            return

        with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
            configs = json.load(f)

        for tenant_id, config in configs.items():
            try:
                self.tenants[tenant_id] = Tenant(tenant_id, config)
                logger.info("Loaded tenant: %s (%s)", tenant_id, config.get("name", ""))
            except Exception as e:
                logger.error("Failed to load tenant %s: %s", tenant_id, e)

    def get(self, tenant_id: str) -> Optional[Tenant]:
        """Get a tenant by ID."""
        return self.tenants.get(tenant_id)

    def list_tenants(self) -> list[dict]:
        """List all tenants (safe info only)."""
        return [t.to_dict() for t in self.tenants.values()]

    def create_tenant(self, tenant_id: str, config: dict) -> Tenant:
        """Create a new tenant."""
        if tenant_id in self.tenants:
            raise ValueError(f"Tenant '{tenant_id}' already exists")
        tenant = Tenant(tenant_id, config)
        self.tenants[tenant_id] = tenant
        self._persist()
        return tenant

    def update_tenant(self, tenant_id: str, config: dict) -> Tenant:
        """Update an existing tenant's configuration."""
        if tenant_id not in self.tenants:
            raise KeyError(f"Tenant '{tenant_id}' not found")
        # Merge with existing config
        existing = self._load_raw_config()
        existing_conf = existing.get(tenant_id, {})
        existing_conf.update(config)
        existing[tenant_id] = existing_conf
        self._save_config(existing)
        # Reload tenant
        self.tenants[tenant_id] = Tenant(tenant_id, existing_conf)
        return self.tenants[tenant_id]

    def delete_tenant(self, tenant_id: str) -> None:
        """Delete a tenant."""
        if tenant_id not in self.tenants:
            raise KeyError(f"Tenant '{tenant_id}' not found")
        del self.tenants[tenant_id]
        self._persist()

    def get_by_telegram_token(self, token: str) -> Optional[Tenant]:
        """Find tenant by Telegram bot token."""
        for tenant in self.tenants.values():
            if tenant.telegram_token == token:
                return tenant
        return None

    def _persist(self) -> None:
        """Save current tenants to config file."""
        raw = {}
        for tid, tenant in self.tenants.items():
            raw[tid] = {
                "name": tenant.name,
                "telegram_token": tenant.telegram_token,
                "claude_api_key": tenant.claude_api_key,
                "claude_model": tenant.claude_model,
                "system_prompt": tenant.system_prompt,
                "enabled": tenant.enabled,
            }
        self._save_config(raw)

    def _load_raw_config(self) -> dict:
        if not self.CONFIG_PATH.exists():
            return {}
        with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_config(self, data: dict) -> None:
        self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
