---
phase: 2
title: "Add /hooks/goconnect Alias"
status: completed
effort: "~25 LOC"
priority: MEDIUM
---

# Phase 2: Add /hooks/goconnect Alias

## Overview

GoClaw uses `/hooks/goconnect` path. DeerFlow uses `/api/channels/goconnect/webhook`. Support both paths for compatibility — existing path stays, add alias.

## Related Code Files

Files to modify:
- `backend/app/gateway/routers/channels.py` — add separate router for `/hooks/goconnect`
- `docker/nginx/nginx.conf` — add nginx location for `/hooks/`

## Implementation Steps

### Step 1: Add hooks router in channels.py

Create a second router with prefix `/hooks` that reuses the same handler functions:

```python
hooks_router = APIRouter(prefix="/hooks", tags=["hooks"])

@hooks_router.post("/goconnect")
async def goconnect_hooks_webhook(request: Request) -> dict:
    """Alias for /api/channels/goconnect/webhook (GoClaw convention)."""
    return await goconnect_webhook(request)

@hooks_router.get("/goconnect")
async def goconnect_hooks_health() -> dict:
    """Health check alias."""
    return await goconnect_webhook_health()
```

### Step 2: Register hooks_router in app.py

File: `backend/app/gateway/app.py`

```python
from app.gateway.routers.channels import hooks_router
app.include_router(hooks_router)
```

### Step 3: Add nginx location for /hooks/

File: `docker/nginx/nginx.conf`, add after the `/api/channels/` location block:

```nginx
# Webhook alias: /hooks/goconnect (GoClaw convention)
location /hooks/ {
    proxy_pass http://gateway;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_connect_timeout 600s;
    proxy_send_timeout 600s;
    proxy_read_timeout 600s;
}
```

## Success Criteria

- [ ] `POST /hooks/goconnect` processes webhook identically to `POST /api/channels/goconnect/webhook`
- [ ] `GET /hooks/goconnect` returns health check
- [ ] Nginx routes `/hooks/` to gateway with 600s timeout
- [ ] Existing `/api/channels/goconnect/webhook` still works (backward compat)
