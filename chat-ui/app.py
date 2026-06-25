"""Optimal chat — a thin, fully-branded chat surface over the gateway.

This is OUR chat client (not Open WebUI): it serves the Optimal-branded UI and
proxies the OpenAI-compatible /v1 surface to the gateway façade *server-side*, so
the upstream key never reaches the browser. It runs on the chat-host bound to
127.0.0.1 only — the same load-bearing boundary Open WebUI had (cloudflared +
Cloudflare Access + Okta are the front door; anything reaching :8080 is trusted).

Identity: Cloudflare Access sets Cf-Access-Authenticated-User-Email; we forward it
upstream so the gateway audit ledger can attribute the call to a person.
"""

from __future__ import annotations

import json
import os

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

FACADE = os.environ.get("FACADE_URL", "http://127.0.0.1:4001").rstrip("/")
KEY = os.environ.get("GATEWAY_BOOTSTRAP_KEY", "")
NAME = os.environ.get("CHAT_NAME", "Optimal")
_STATIC = os.path.join(os.path.dirname(__file__), "static")
_EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"

app = FastAPI(title=f"{NAME} Chat", docs_url=None, redoc_url=None)
_client = httpx.AsyncClient(base_url=FACADE, timeout=httpx.Timeout(600.0, connect=10.0))


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "service": NAME}


@app.get("/config", include_in_schema=False)
async def config(user: str = Header("", alias=_EMAIL_HEADER)):
    return {"name": NAME, "user": user}


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(os.path.join(_STATIC, "index.html"))


@app.get("/v1/models", include_in_schema=False)
async def models():
    r = await _client.get("/v1/models", headers={"authorization": f"Bearer {KEY}"})
    return JSONResponse(_safe_json(r), status_code=r.status_code)


@app.post("/v1/chat/completions", include_in_schema=False)
async def chat(request: Request, user: str = Header("", alias=_EMAIL_HEADER)):
    body = await request.body()
    headers = {"authorization": f"Bearer {KEY}", "content-type": "application/json"}
    if user:
        # Forward the Access-verified identity for the gateway audit trail.
        headers["x-openwebui-user-email"] = user
        headers["x-optimal-user-email"] = user

    req = _client.build_request("POST", "/v1/chat/completions", content=body, headers=headers)
    upstream = await _client.send(req, stream=True)

    if upstream.status_code != 200:
        raw = await upstream.aread()
        await upstream.aclose()
        try:
            return JSONResponse(json.loads(raw or b"{}"), status_code=upstream.status_code)
        except ValueError:
            return JSONResponse(
                {"error": {"message": raw.decode("utf-8", "replace")[:500] or "upstream error",
                           "type": "upstream_error"}},
                status_code=upstream.status_code)

    async def stream():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        stream(), status_code=200,
        media_type=upstream.headers.get("content-type", "text/event-stream"))


app.mount("/static", StaticFiles(directory=_STATIC), name="static")


def _safe_json(r: httpx.Response):
    try:
        return r.json()
    except ValueError:
        return {"data": []}
