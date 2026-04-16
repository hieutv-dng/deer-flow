---
phase: 3
title: "Add Webhook Route"
status: done
effort: "~40 LOC"
---

# Phase 3: Add Webhook Route

## Overview

Add POST webhook endpoint to Gateway FastAPI for GoConnect inbound messages. This is DeerFlow's first webhook-based channel.

## Context

GoConnect Chat Service sends POST requests when user @mentions bot. Gateway receives, validates, forwards to channel.

**Reference:** goclaw `handlers.go` → `handleWebhookHTTP()` + `WebhookHandler()`

## Related Code Files

- **Edit:** `backend/app/gateway/routers/channels.py`

## Implementation Steps

### 1. Add webhook POST endpoint

```python
from fastapi import Request

@router.post("/goconnect/webhook")
async def goconnect_webhook(request: Request) -> dict:
    """Receive inbound messages from GoConnect Chat Service."""
    from app.channels.service import get_channel_service

    service = get_channel_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Channel service not running")

    channel = service.get_channel("goconnect")
    if channel is None:
        raise HTTPException(status_code=503, detail="GoConnect channel not available")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    result = await channel.handle_webhook(payload)
    return result
```

### 2. Health check GET endpoint

```python
@router.get("/goconnect/webhook")
async def goconnect_webhook_health() -> dict:
    return {"status": "ok", "channel": "goconnect", "type": "goconnect"}
```

### Design notes

- Token validation inside `GoConnectChannel.handle_webhook()`, not route
- FastAPI default body limit handles 1MB cap
- Route returns immediately after publishing to bus (async processing)
- GET for health checks (matching goclaw pattern)

## Success Criteria

- [ ] `POST /api/channels/goconnect/webhook` receives and forwards payloads
- [ ] `GET /api/channels/goconnect/webhook` returns health status
- [ ] Invalid payloads return 400
- [ ] Missing channel service returns 503
