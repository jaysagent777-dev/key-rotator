import os
import time
import json
from contextlib import asynccontextmanager

import litellm
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from key_manager import add_key, delete_key, pick_key, mark_error, get_stats, get_all_keys
from providers import PROVIDERS, MODEL_ALIASES

load_dotenv()
litellm.set_verbose = False

PORT = int(os.getenv("PORT", 7860))

templates = Jinja2Templates(directory="templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed keys from .env on startup
    for provider, cfg in PROVIDERS.items():
        env_val = os.getenv(cfg["env_key"], "")
        if env_val:
            for key in [k.strip() for k in env_val.split(",") if k.strip()]:
                add_key(provider, key, label=f"{provider}-env")
    yield


app = FastAPI(title="Key Rotator", lifespan=lifespan)


# ─── OpenAI-compatible proxy ─────────────────────────────────────────────────

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model_alias = body.get("model", "gpt-4o-mini")

    # Resolve model alias → provider + litellm model
    if model_alias in MODEL_ALIASES:
        provider, litellm_model = MODEL_ALIASES[model_alias]
    else:
        # Try to infer provider from model string (e.g. "groq/llama3-8b-8192")
        if "/" in model_alias:
            provider = model_alias.split("/")[0]
            litellm_model = model_alias
        else:
            # Default to first provider that has keys
            all_keys = get_all_keys()
            provider = next((p for p in PROVIDERS if all_keys.get(p)), None)
            if not provider:
                raise HTTPException(503, "No keys configured. Add keys via the dashboard.")
            litellm_model = PROVIDERS[provider]["default_model"]

    max_retries = min(3, len(get_all_keys().get(provider, [])) or 1)
    last_error = None

    for attempt in range(max_retries):
        api_key = pick_key(provider)
        if not api_key:
            raise HTTPException(503, f"No keys available for provider '{provider}'.")

        try:
            kwargs = {
                "model": litellm_model,
                "messages": body.get("messages", []),
                "api_key": api_key,
                "stream": body.get("stream", False),
            }
            for opt in ("temperature", "max_tokens", "top_p", "stop"):
                if opt in body:
                    kwargs[opt] = body[opt]

            response = await litellm.acompletion(**kwargs)
            return JSONResponse(content=response.model_dump())

        except litellm.RateLimitError:
            mark_error(provider, api_key, cooldown_seconds=60)
            last_error = "rate_limit"
        except litellm.AuthenticationError:
            mark_error(provider, api_key, cooldown_seconds=3600)
            last_error = "auth"
            break
        except Exception as e:
            last_error = str(e)
            break

    raise HTTPException(429 if last_error == "rate_limit" else 502,
                        f"All keys exhausted or failed. Last error: {last_error}")


@app.get("/v1/models")
async def list_models():
    models = []
    for alias in MODEL_ALIASES:
        models.append({"id": alias, "object": "model", "owned_by": "key-rotator"})
    for p, cfg in PROVIDERS.items():
        models.append({"id": cfg["default_model"], "object": "model", "owned_by": p})
    return {"object": "list", "data": models}


# ─── Dashboard ────────────────────────────────────────────────────────────────

def _global_stats():
    stats = get_stats()
    total_keys = sum(len(v) for v in stats.values())
    total_requests = sum(k["requests"] for v in stats.values() for k in v)
    total_errors = sum(k["errors"] for v in stats.values() for k in v)
    return stats, total_keys, total_requests, total_errors


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats, total_keys, total_requests, total_errors = _global_stats()
    all_keys_flat = [k for keys in stats.values() for k in keys]
    max_requests = max((k["requests"] for k in all_keys_flat), default=1) or 1
    chart_data = {
        p: {
            "requests": sum(k["requests"] for k in keys),
            "errors": sum(k["errors"] for k in keys),
        }
        for p, keys in stats.items()
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "providers": list(PROVIDERS.keys()),
        "total_keys": total_keys,
        "total_requests": total_requests,
        "total_errors": total_errors,
        "provider_count": len([p for p in PROVIDERS if stats.get(p)]),
        "port": PORT,
        "max_requests": max_requests,
        "chart_data": chart_data,
    })


@app.get("/dashboard/keys-partial", response_class=HTMLResponse)
async def keys_partial(request: Request):
    stats = get_stats()
    return templates.TemplateResponse("keys_partial.html", {"request": request, "stats": stats})


@app.post("/dashboard/add-key", response_class=HTMLResponse)
async def dashboard_add_key(
    provider: str = Form(...),
    key: str = Form(...),
    label: str = Form(""),
):
    if provider not in PROVIDERS:
        return HTMLResponse(f'<span style="color:#f77">Unknown provider: {provider}</span>')
    result = add_key(provider, key.strip(), label.strip())
    if result["status"] == "duplicate":
        return HTMLResponse('<span style="color:#f7c948">Key already exists.</span>')
    return HTMLResponse(f'<span style="color:#7cf79e">✓ Added key to {provider}.</span>')


@app.delete("/dashboard/delete-key", response_class=HTMLResponse)
async def dashboard_delete_key(
    provider: str = Form(...),
    key: str = Form(...),
):
    delete_key(provider, key)
    return HTMLResponse("")


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    stats = get_stats()
    return {
        "status": "ok",
        "providers": {p: len(keys) for p, keys in stats.items()},
        "timestamp": time.time(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
