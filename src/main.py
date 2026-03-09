"""Meoxa Chatbot - Entry point."""

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv

from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from src.core.tenant import TenantManager
from src.adapters.telegram import TelegramAdapter
from src.api import routes

load_dotenv()

# --- Logging ---
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("meoxa")

# --- Globals ---
tenant_manager = TenantManager()
telegram_adapter = TelegramAdapter(tenant_manager)


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan - start/stop Telegram bots alongside the API."""
    # Startup
    logger.info("Starting Meoxa Chatbot...")
    routes.tenant_manager = tenant_manager
    routes.telegram_adapter = telegram_adapter
    routes.ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

    if not routes.ADMIN_API_KEY:
        logger.warning("ADMIN_API_KEY not set - API is unprotected!")

    await telegram_adapter.start_all()
    logger.info(
        "Started %d Telegram bot(s)", len(telegram_adapter.get_running_bots())
    )

    yield

    # Shutdown
    logger.info("Shutting down...")
    await telegram_adapter.stop_all()


# Apply lifespan to FastAPI app
routes.app.router.lifespan_context = lifespan

# Serve admin frontend
routes.app.mount("/static", StaticFiles(directory="static"), name="static")


@routes.app.get("/admin")
async def admin_redirect():
    return RedirectResponse(url="/static/admin.html")


def main():
    """Run the application."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    logger.info("Meoxa Chatbot starting on %s:%d", host, port)
    uvicorn.run(
        routes.app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
