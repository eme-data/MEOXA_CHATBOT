"""Telegram bot adapter - manages multiple bot instances (one per tenant)."""

import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from src.core.tenant import Tenant, TenantManager

logger = logging.getLogger(__name__)


class TelegramAdapter:
    """Manages Telegram bot instances for all tenants."""

    def __init__(self, tenant_manager: TenantManager):
        self.tenant_manager = tenant_manager
        self._apps: dict[str, Application] = {}

    async def start_all(self) -> None:
        """Start Telegram bots for all enabled tenants with a token."""
        for tenant_id, tenant in self.tenant_manager.tenants.items():
            if tenant.enabled and tenant.telegram_token:
                await self.start_bot(tenant)

    async def start_bot(self, tenant: Tenant) -> None:
        """Start a single Telegram bot for a tenant."""
        if tenant.tenant_id in self._apps:
            logger.warning("Bot already running for tenant %s", tenant.tenant_id)
            return

        if not tenant.telegram_token:
            logger.warning("No Telegram token for tenant %s", tenant.tenant_id)
            return

        app = Application.builder().token(tenant.telegram_token).build()

        # Bind tenant to handlers via closure
        app.add_handler(CommandHandler("start", self._make_start_handler(tenant)))
        app.add_handler(CommandHandler("help", self._make_help_handler(tenant)))
        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._make_message_handler(tenant),
            )
        )

        self._apps[tenant.tenant_id] = app

        # Initialize and start polling
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        logger.info("Telegram bot started for tenant: %s (%s)", tenant.tenant_id, tenant.name)

    async def stop_bot(self, tenant_id: str) -> None:
        """Stop a single tenant's bot."""
        app = self._apps.pop(tenant_id, None)
        if app:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            logger.info("Telegram bot stopped for tenant: %s", tenant_id)

    async def stop_all(self) -> None:
        """Stop all running bots."""
        tenant_ids = list(self._apps.keys())
        for tenant_id in tenant_ids:
            await self.stop_bot(tenant_id)

    def _make_start_handler(self, tenant: Tenant):
        async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            welcome = f"Bienvenue ! Je suis le bot de {tenant.name}. Comment puis-je vous aider ?"
            await update.message.reply_text(welcome)
        return handler

    def _make_help_handler(self, tenant: Tenant):
        async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            help_text = (
                "Envoyez-moi un message et je ferai de mon mieux pour vous répondre.\n"
                "Commandes disponibles :\n"
                "/start - Démarrer la conversation\n"
                "/help - Afficher cette aide"
            )
            await update.message.reply_text(help_text)
        return handler

    def _make_message_handler(self, tenant: Tenant):
        async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_message = update.message.text
            user_id = str(update.effective_user.id)

            response = await tenant.engine.handle_message(user_message, user_id)
            await update.message.reply_text(response)
        return handler

    def get_running_bots(self) -> list[str]:
        """Return list of tenant IDs with running bots."""
        return list(self._apps.keys())
