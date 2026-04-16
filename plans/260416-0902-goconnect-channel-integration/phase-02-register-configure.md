---
phase: 2
title: "Register & Configure"
status: done
effort: "~20 LOC"
---

# Phase 2: Register & Configure

## Overview

Register GoConnect in channel registry, capabilities map, and add config example. Minimal edits across 3 files.

## Related Code Files

- **Edit:** `backend/app/channels/service.py` (line 17-24: `_CHANNEL_REGISTRY`)
- **Edit:** `backend/app/channels/manager.py` (line 37-44: `CHANNEL_CAPABILITIES`)
- **Edit:** `config.example.yaml` (channels section, after wecom/wechat block)

## Implementation Steps

### 1. Add to `_CHANNEL_REGISTRY` in `service.py`

```python
_CHANNEL_REGISTRY: dict[str, str] = {
    ...
    "goconnect": "app.channels.goconnect:GoConnectChannel",
}
```

### 2. Add to `CHANNEL_CAPABILITIES` in `manager.py`

```python
CHANNEL_CAPABILITIES = {
    ...
    "goconnect": {"supports_streaming": False},
}
```

GoConnect uses `runs.wait()` — no streaming (Chat Service doesn't support incremental card updates like Feishu).

### 3. Add config example in `config.example.yaml`

Add after the wecom/wechat block:

```yaml
#   goconnect:
#     enabled: false
#     base_url: $GOCONNECT_BASE_URL              # Chat Service URL
#     api_key: $GOCONNECT_API_KEY                 # licenseKey for WebHookGuard auth
#     webhook_token: $GOCONNECT_WEBHOOK_TOKEN     # shared secret for inbound webhook
#     bot_user_id: $GOCONNECT_BOT_USER_ID         # UUID of bot user
#     bot_user_code: $GOCONNECT_BOT_USER_CODE     # Convention: BOT_*
```

## Success Criteria

- [ ] `"goconnect"` in `_CHANNEL_REGISTRY` pointing to `GoConnectChannel`
- [ ] `"goconnect"` in `CHANNEL_CAPABILITIES` with `supports_streaming: False`
- [ ] `config.example.yaml` has goconnect section with all config keys documented
