---
phase: 1
title: "Implement GoConnect Channel"
status: done
effort: "~180 LOC"
---

# Phase 1: Implement GoConnect Channel

## Overview

Create `backend/app/channels/goconnect.py` — the core GoConnect channel class. Port from goclaw Go implementation, adapting to DeerFlow's `Channel` ABC pattern.

## Context

**Reference implementation:** `/Users/hieutv/Documents/workspace/hieutv-dng@github.com/goclaw/internal/channels/goconnect/`
- `channel.go` → Channel struct, lifecycle, doAPICall, retrySend
- `handlers.go` → Webhook payload parsing, inbound message handling
- `send.go` → Text send, file upload (3-step presigned URL flow)
- `format.go` → Markdown conversion (skip — minimal value in DeerFlow)

**DeerFlow patterns to follow:**
- `backend/app/channels/discord.py` — closest pattern (also uses separate thread for client)
- `backend/app/channels/base.py` — abstract Channel class
- `backend/app/channels/message_bus.py` — InboundMessage, OutboundMessage, ResolvedAttachment

## Related Code Files

- **Create:** `backend/app/channels/goconnect.py`
- **Read:** `backend/app/channels/base.py`, `backend/app/channels/discord.py`, `backend/app/channels/manager.py`

## Implementation Steps

### 1. GoConnectChannel class skeleton

```python
class GoConnectChannel(Channel):
    def __init__(self, bus: MessageBus, config: dict[str, Any]) -> None:
        super().__init__(name="goconnect", bus=bus, config=config)
        self._base_url = str(config.get("base_url", "")).rstrip("/")
        self._api_key = str(config.get("api_key", ""))
        self._webhook_token = str(config.get("webhook_token", ""))
        self._bot_user_id = str(config.get("bot_user_id", ""))
        self._bot_user_code = str(config.get("bot_user_code", ""))
        self._http_client: httpx.AsyncClient | None = None
```

### 2. Lifecycle methods

- `start()`: Validate config (base_url, api_key, bot_user_id required). Create `httpx.AsyncClient`. Subscribe outbound. Set `_running = True`.
- `stop()`: Unsubscribe outbound. Close httpx client. Set `_running = False`.

Unlike Telegram/Discord, GoConnect does NOT need a background polling thread — inbound comes via webhook.
<!-- Updated: Validation Session 1 - Confirmed: no access control filtering, accept all users. Log & drop on outbound errors, no retry. -->

### 3. Webhook handler method

```python
async def handle_webhook(self, payload: dict[str, Any]) -> dict[str, str]:
```

Called by Gateway FastAPI route (phase 3). Steps:
1. Validate webhook token from payload `token` field
2. Validate required fields: `room_id`, `user_id`, `message`
3. Determine msg_type: command if starts with `/`, else chat
4. Build InboundMessage via `_make_inbound()`
   - `chat_id` = `room_id`
   - `user_id` = `user_id`
   - `text` = `message`
   - `thread_ts` = None (GoConnect không dùng thread concept giống Discord)
   - `topic_id` = `room_id` (reuse same DeerFlow thread per room)
   - `metadata` = `{room_id, user_id, user_name, bot_user_id, bot_user_code, message_created_date, room_type}`
5. Publish inbound to bus
6. Return `{"status": "accepted"}`

**Mapping from goclaw `handleInboundMessage()`:**
- Skip: DM/Group policy checking → dùng pattern đơn giản hơn
- Skip: Group history context building → DeerFlow manages via thread
- Skip: Contact collector → DeerFlow không có
- Keep: metadata pass-through (room_id, user_name, message_created_date)

### 4. Outbound send method

```python
async def send(self, msg: OutboundMessage) -> None:
```

Port from goclaw `sendTextMessage()`:
1. Extract `room_id` from `msg.chat_id`
2. Resolve bot identity from config
3. Build `webhookResponsePayload` dict
4. POST to `/api/v1/chatservice/goclaw-connector/webhook/response`
5. Include `api-key` header
6. Handle text chunking (5000 char limit per message)

### 5. File upload method

```python
async def send_file(self, msg: OutboundMessage, attachment: ResolvedAttachment) -> bool:
```

Port from goclaw 3-step presigned URL flow:
1. `POST /webhook/file-init` → get presigned URL + file_id + object_key
2. `PUT` binary to presigned URL
3. `POST /webhook/file-commit` → confirm upload

### 6. Helper: _api_call

```python
async def _api_call(self, method: str, path: str, payload: dict | None = None) -> bytes:
```

Port from goclaw `doAPICall()`. Uses httpx async. Sets `api-key` header.

## Success Criteria

- [ ] `GoConnectChannel` class created in `backend/app/channels/goconnect.py`
- [ ] Implements all abstract methods: `start()`, `stop()`, `send()`
- [ ] `send_file()` implements 3-step presigned URL flow
- [ ] `handle_webhook()` parses payload and publishes to bus
- [ ] File stays under 200 LOC (modularize if exceeds)
- [ ] No imports from goclaw — clean port to Python
