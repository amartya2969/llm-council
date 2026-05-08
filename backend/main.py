from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os
import pathlib
from dotenv import load_dotenv

load_dotenv()

import providers
import council as council_mod

# Pre-load keys from environment if present
if os.getenv("ANTHROPIC_API_KEY"):
    providers.set_key("anthropic", os.getenv("ANTHROPIC_API_KEY"))
if os.getenv("OPENAI_API_KEY"):
    providers.set_key("openai", os.getenv("OPENAI_API_KEY"))
if os.getenv("GEMINI_API_KEY"):
    providers.set_key("gemini", os.getenv("GEMINI_API_KEY"))

app = FastAPI(title="LLM Council")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = pathlib.Path(__file__).parent.parent / "frontend"


# ─── Pydantic models ──────────────────────────────────────────────────────────

class KeysPayload(BaseModel):
    anthropic: Optional[str] = None
    openai: Optional[str] = None
    gemini: Optional[str] = None


class RunPayload(BaseModel):
    query: str
    active_models: list[str]
    chairman_model: str = providers.DEFAULT_CHAIRMAN_KEY


class ModelResponseOut(BaseModel):
    model_key: str
    display_name: str
    response: str
    error: Optional[str] = None


class CouncilResultOut(BaseModel):
    query: str
    stage1: list[ModelResponseOut]
    stage2: list[ModelResponseOut]
    chairman_synthesis: str
    chairman_model: str
    error: Optional[str] = None


# ─── Config endpoints ─────────────────────────────────────────────────────────

@app.get("/api/models")
def list_models():
    """Return the full model catalogue with provider info."""
    return providers.MODELS


@app.post("/api/keys")
def update_keys(payload: KeysPayload):
    """Store API keys in memory for this session."""
    if payload.anthropic:
        providers.set_key("anthropic", payload.anthropic)
    if payload.openai:
        providers.set_key("openai", payload.openai)
    if payload.gemini:
        providers.set_key("gemini", payload.gemini)
    return {"status": "ok"}


@app.get("/api/keys/status")
def keys_status():
    """Return which providers have keys configured (without exposing the keys)."""
    return {
        "anthropic": bool(providers.get_key("anthropic")),
        "openai": bool(providers.get_key("openai")),
        "gemini": bool(providers.get_key("gemini")),
    }


# ─── Council endpoint ─────────────────────────────────────────────────────────

@app.post("/api/council/run", response_model=CouncilResultOut)
async def run_council(payload: RunPayload):
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    if not payload.active_models:
        raise HTTPException(status_code=400, detail="Select at least one model")

    if payload.chairman_model not in providers.MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown chairman model: {payload.chairman_model}")

    result = await council_mod.run_council(
        query=payload.query,
        active_models=payload.active_models,
        chairman_key=payload.chairman_model,
    )

    return CouncilResultOut(
        query=result.query,
        stage1=[ModelResponseOut(**vars(r)) for r in result.stage1],
        stage2=[ModelResponseOut(**vars(r)) for r in result.stage2],
        chairman_synthesis=result.chairman_synthesis,
        chairman_model=payload.chairman_model,
        error=result.error,
    )


# ─── Serve frontend ───────────────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
