"""REST API for chatbot administration - multi-tenant management."""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.core.tenant import TenantManager

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Meoxa Chatbot API",
    description="API d'administration pour le chatbot multi-tenant Meoxa",
    version="1.0.0",
)

# CORS for widget embedding on any domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Global references (set from main.py at startup)
tenant_manager: Optional[TenantManager] = None
telegram_adapter = None


def get_tenant_manager() -> TenantManager:
    if tenant_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return tenant_manager


# --- Auth ---

ADMIN_API_KEY: Optional[str] = None


async def verify_admin_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """Simple API key auth for admin endpoints."""
    if ADMIN_API_KEY and x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key


# --- Models ---

class TenantCreate(BaseModel):
    tenant_id: str
    name: str
    telegram_token: Optional[str] = None
    claude_api_key: Optional[str] = None
    claude_model: str = "claude-sonnet-4-20250514"
    system_prompt: str = "Tu es un assistant utile et professionnel."
    enabled: bool = True


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    telegram_token: Optional[str] = None
    claude_api_key: Optional[str] = None
    claude_model: Optional[str] = None
    system_prompt: Optional[str] = None
    enabled: Optional[bool] = None


class RuleCreate(BaseModel):
    patterns: list[str]
    response: str


class MessageTest(BaseModel):
    message: str
    user_id: str = "test-user"


class WidgetMessage(BaseModel):
    message: str
    session_id: str = ""


class KnowledgeEntry(BaseModel):
    title: str
    content: str
    category: str = "general"


# --- Health ---

@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Tenant management ---

@app.get("/api/tenants", dependencies=[Depends(verify_admin_key)])
async def list_tenants(tm: TenantManager = Depends(get_tenant_manager)):
    return {"tenants": tm.list_tenants()}


@app.post("/api/tenants", dependencies=[Depends(verify_admin_key)])
async def create_tenant(
    data: TenantCreate,
    tm: TenantManager = Depends(get_tenant_manager),
):
    try:
        tenant = tm.create_tenant(data.tenant_id, data.model_dump(exclude={"tenant_id"}))
        # Start Telegram bot if token provided
        if tenant.telegram_token and telegram_adapter:
            await telegram_adapter.start_bot(tenant)
        return {"tenant": tenant.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/tenants/{tenant_id}", dependencies=[Depends(verify_admin_key)])
async def get_tenant(
    tenant_id: str,
    tm: TenantManager = Depends(get_tenant_manager),
):
    tenant = tm.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"tenant": tenant.to_dict()}


@app.put("/api/tenants/{tenant_id}", dependencies=[Depends(verify_admin_key)])
async def update_tenant(
    tenant_id: str,
    data: TenantUpdate,
    tm: TenantManager = Depends(get_tenant_manager),
):
    try:
        update_data = data.model_dump(exclude_none=True)
        tenant = tm.update_tenant(tenant_id, update_data)

        # Restart Telegram bot if token changed
        if "telegram_token" in update_data and telegram_adapter:
            await telegram_adapter.stop_bot(tenant_id)
            if tenant.telegram_token:
                await telegram_adapter.start_bot(tenant)

        return {"tenant": tenant.to_dict()}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/tenants/{tenant_id}", dependencies=[Depends(verify_admin_key)])
async def delete_tenant(
    tenant_id: str,
    tm: TenantManager = Depends(get_tenant_manager),
):
    try:
        if telegram_adapter:
            await telegram_adapter.stop_bot(tenant_id)
        tm.delete_tenant(tenant_id)
        return {"status": "deleted"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Scripted rules management (per tenant) ---

@app.get("/api/tenants/{tenant_id}/rules", dependencies=[Depends(verify_admin_key)])
async def list_rules(
    tenant_id: str,
    tm: TenantManager = Depends(get_tenant_manager),
):
    tenant = tm.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"rules": tenant.engine.scripted.get_rules()}


@app.post("/api/tenants/{tenant_id}/rules", dependencies=[Depends(verify_admin_key)])
async def add_rule(
    tenant_id: str,
    data: RuleCreate,
    tm: TenantManager = Depends(get_tenant_manager),
):
    tenant = tm.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    rule = tenant.engine.scripted.add_rule(data.patterns, data.response)
    return {"rule": rule}


@app.put("/api/tenants/{tenant_id}/rules/{rule_index}", dependencies=[Depends(verify_admin_key)])
async def update_rule(
    tenant_id: str,
    rule_index: int,
    data: RuleCreate,
    tm: TenantManager = Depends(get_tenant_manager),
):
    tenant = tm.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    try:
        rule = tenant.engine.scripted.update_rule(rule_index, data.patterns, data.response)
        return {"rule": rule}
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/tenants/{tenant_id}/rules/{rule_index}", dependencies=[Depends(verify_admin_key)])
async def delete_rule(
    tenant_id: str,
    rule_index: int,
    tm: TenantManager = Depends(get_tenant_manager),
):
    tenant = tm.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    try:
        tenant.engine.scripted.delete_rule(rule_index)
        return {"status": "deleted"}
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Test endpoint ---

@app.post("/api/tenants/{tenant_id}/test", dependencies=[Depends(verify_admin_key)])
async def test_message(
    tenant_id: str,
    data: MessageTest,
    tm: TenantManager = Depends(get_tenant_manager),
):
    """Test a message against a tenant's chatbot engine."""
    tenant = tm.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    response = await tenant.engine.handle_message(data.message, data.user_id)
    return {"response": response}


# --- Bot status ---

@app.get("/api/bots/status", dependencies=[Depends(verify_admin_key)])
async def bots_status():
    """Get running Telegram bots status."""
    running = telegram_adapter.get_running_bots() if telegram_adapter else []
    return {"running_bots": running}


# --- Knowledge base management (per tenant) ---

@app.get("/api/tenants/{tenant_id}/knowledge", dependencies=[Depends(verify_admin_key)])
async def list_knowledge(
    tenant_id: str,
    tm: TenantManager = Depends(get_tenant_manager),
):
    tenant = tm.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"entries": tenant.engine.knowledge.get_entries()}


@app.post("/api/tenants/{tenant_id}/knowledge", dependencies=[Depends(verify_admin_key)])
async def add_knowledge(
    tenant_id: str,
    data: KnowledgeEntry,
    tm: TenantManager = Depends(get_tenant_manager),
):
    tenant = tm.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    entry = tenant.engine.knowledge.add_entry(data.title, data.content, data.category)
    return {"entry": entry}


@app.put("/api/tenants/{tenant_id}/knowledge/{entry_id}", dependencies=[Depends(verify_admin_key)])
async def update_knowledge(
    tenant_id: str,
    entry_id: int,
    data: KnowledgeEntry,
    tm: TenantManager = Depends(get_tenant_manager),
):
    tenant = tm.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    try:
        entry = tenant.engine.knowledge.update_entry(entry_id, data.title, data.content, data.category)
        return {"entry": entry}
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/tenants/{tenant_id}/knowledge/{entry_id}", dependencies=[Depends(verify_admin_key)])
async def delete_knowledge(
    tenant_id: str,
    entry_id: int,
    tm: TenantManager = Depends(get_tenant_manager),
):
    tenant = tm.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    try:
        tenant.engine.knowledge.delete_entry(entry_id)
        return {"status": "deleted"}
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# PUBLIC WIDGET API - No admin auth, accessible from client sites
# ============================================================

@app.post("/widget/{tenant_id}/chat")
async def widget_chat(
    tenant_id: str,
    data: WidgetMessage,
    tm: TenantManager = Depends(get_tenant_manager),
):
    """Public endpoint for the embeddable chat widget."""
    tenant = tm.get(tenant_id)
    if not tenant or not tenant.enabled:
        raise HTTPException(status_code=404, detail="Chat not available")
    session_id = data.session_id or "widget-anonymous"
    response = await tenant.engine.handle_message(data.message, session_id)
    return {"response": response}


@app.get("/widget/{tenant_id}/config")
async def widget_config(
    tenant_id: str,
    tm: TenantManager = Depends(get_tenant_manager),
):
    """Return public widget configuration (theme, welcome message, etc.)."""
    tenant = tm.get(tenant_id)
    if not tenant or not tenant.enabled:
        raise HTTPException(status_code=404, detail="Chat not available")
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "welcome_message": f"Bonjour ! Je suis l'assistant de {tenant.name}. Comment puis-je vous aider ?",
    }


@app.get("/widget/{tenant_id}/embed.js")
async def widget_embed_script(
    tenant_id: str,
    request: Request,
    tm: TenantManager = Depends(get_tenant_manager),
):
    """Serve the embeddable JS widget script, configured for this tenant."""
    tenant = tm.get(tenant_id)
    if not tenant or not tenant.enabled:
        raise HTTPException(status_code=404, detail="Chat not available")

    base_url = str(request.base_url).rstrip("/")
    script = WIDGET_JS_TEMPLATE.replace("{{TENANT_ID}}", tenant_id).replace(
        "{{BASE_URL}}", base_url
    )
    return Response(content=script, media_type="application/javascript")


# --- Embeddable widget JS (self-contained) ---

WIDGET_JS_TEMPLATE = """
(function() {
  const TENANT_ID = "{{TENANT_ID}}";
  const BASE_URL = "{{BASE_URL}}";
  const SESSION_ID = "meoxa-" + Math.random().toString(36).substr(2, 9);

  // Styles
  const style = document.createElement("style");
  style.textContent = `
    #meoxa-chat-widget {
      position: fixed;
      bottom: 20px;
      right: 20px;
      z-index: 99999;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    #meoxa-chat-toggle {
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: #2563eb;
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.2s;
    }
    #meoxa-chat-toggle:hover { transform: scale(1.1); }
    #meoxa-chat-toggle svg { width: 28px; height: 28px; fill: white; }
    #meoxa-chat-box {
      display: none;
      position: absolute;
      bottom: 70px;
      right: 0;
      width: 370px;
      max-width: 90vw;
      height: 500px;
      max-height: 70vh;
      background: #fff;
      border-radius: 16px;
      box-shadow: 0 8px 30px rgba(0,0,0,0.12);
      flex-direction: column;
      overflow: hidden;
    }
    #meoxa-chat-box.open { display: flex; }
    #meoxa-chat-header {
      background: #2563eb;
      color: white;
      padding: 16px;
      font-size: 15px;
      font-weight: 600;
    }
    #meoxa-chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .meoxa-msg {
      max-width: 80%;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 14px;
      line-height: 1.4;
      word-wrap: break-word;
    }
    .meoxa-msg.user {
      align-self: flex-end;
      background: #2563eb;
      color: white;
      border-bottom-right-radius: 4px;
    }
    .meoxa-msg.bot {
      align-self: flex-start;
      background: #f1f5f9;
      color: #1e293b;
      border-bottom-left-radius: 4px;
    }
    #meoxa-chat-input-area {
      display: flex;
      padding: 12px;
      border-top: 1px solid #e2e8f0;
      gap: 8px;
    }
    #meoxa-chat-input {
      flex: 1;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 14px;
      outline: none;
    }
    #meoxa-chat-input:focus { border-color: #2563eb; }
    #meoxa-chat-send {
      background: #2563eb;
      color: white;
      border: none;
      border-radius: 8px;
      padding: 8px 16px;
      cursor: pointer;
      font-size: 14px;
    }
    #meoxa-chat-send:hover { background: #1d4ed8; }
    #meoxa-chat-send:disabled { opacity: 0.5; cursor: not-allowed; }
  `;
  document.head.appendChild(style);

  // HTML
  const widget = document.createElement("div");
  widget.id = "meoxa-chat-widget";
  widget.innerHTML = `
    <div id="meoxa-chat-box">
      <div id="meoxa-chat-header">Assistant</div>
      <div id="meoxa-chat-messages"></div>
      <div id="meoxa-chat-input-area">
        <input id="meoxa-chat-input" type="text" placeholder="Votre message..." autocomplete="off" />
        <button id="meoxa-chat-send">Envoyer</button>
      </div>
    </div>
    <button id="meoxa-chat-toggle">
      <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
    </button>
  `;
  document.body.appendChild(widget);

  const chatBox = document.getElementById("meoxa-chat-box");
  const toggle = document.getElementById("meoxa-chat-toggle");
  const messages = document.getElementById("meoxa-chat-messages");
  const input = document.getElementById("meoxa-chat-input");
  const sendBtn = document.getElementById("meoxa-chat-send");

  // Load config and show welcome
  fetch(BASE_URL + "/widget/" + TENANT_ID + "/config")
    .then(r => r.json())
    .then(cfg => {
      document.getElementById("meoxa-chat-header").textContent = cfg.name || "Assistant";
      addMessage(cfg.welcome_message, "bot");
    })
    .catch(() => addMessage("Bienvenue ! Comment puis-je vous aider ?", "bot"));

  toggle.addEventListener("click", () => chatBox.classList.toggle("open"));

  function addMessage(text, type) {
    const div = document.createElement("div");
    div.className = "meoxa-msg " + type;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    addMessage(text, "user");
    input.value = "";
    sendBtn.disabled = true;

    try {
      const res = await fetch(BASE_URL + "/widget/" + TENANT_ID + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: SESSION_ID })
      });
      const data = await res.json();
      addMessage(data.response, "bot");
    } catch (e) {
      addMessage("Erreur de connexion. Veuillez r\\u00e9essayer.", "bot");
    }
    sendBtn.disabled = false;
    input.focus();
  }

  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter") sendMessage();
  });
})();
"""
