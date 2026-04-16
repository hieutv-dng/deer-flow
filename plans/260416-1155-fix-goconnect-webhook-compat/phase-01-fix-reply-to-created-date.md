---
phase: 1
title: "Fix reply_to_created_date"
status: completed
effort: "~15 LOC"
priority: HIGH
---

# Phase 1: Fix reply_to_created_date

## Overview

GoConnect Chat Service uses `reply_to_created_date` to thread-reply responses to the original message. GoClaw passes `message_created_date` from inbound → outbound metadata and includes it in the first text chunk. DeerFlow currently drops metadata between inbound and outbound, so responses appear as floating messages.

## Context Links

- GoClaw reference: `goclaw/internal/channels/goconnect/handlers.go:222-223` (metadata["reply_to_created_date"] = payload.MessageCreatedDate)
- GoClaw reference: `goclaw/internal/channels/goconnect/send.go:126-131` (only first chunk carries reply_to)

## Related Code Files

Files to modify:
- `backend/app/channels/manager.py` — pass `metadata` from InboundMessage to OutboundMessage
- `backend/app/channels/goconnect.py` — include `reply_to_created_date` in outbound payload

Files to read:
- `backend/app/channels/message_bus.py` — InboundMessage/OutboundMessage both have `metadata: dict`
- `backend/app/channels/base.py` — `_on_outbound()` passes `msg` to `send()`, metadata flows through

## Implementation Steps

### Step 1: Pass metadata in manager.py (non-streaming path)

File: `backend/app/channels/manager.py`, line 756-764

```python
# BEFORE:
outbound = OutboundMessage(
    channel_name=msg.channel_name,
    chat_id=msg.chat_id,
    thread_id=thread_id,
    text=response_text,
    artifacts=artifacts,
    attachments=attachments,
    thread_ts=msg.thread_ts,
)

# AFTER — add metadata:
outbound = OutboundMessage(
    channel_name=msg.channel_name,
    chat_id=msg.chat_id,
    thread_id=thread_id,
    text=response_text,
    artifacts=artifacts,
    attachments=attachments,
    thread_ts=msg.thread_ts,
    metadata=msg.metadata,
)
```

### Step 2: Pass metadata in manager.py (streaming final message)

File: `backend/app/channels/manager.py`, line 859-869

```python
# Add metadata=msg.metadata to the final OutboundMessage in _handle_streaming_chat
```

**Note:** Streaming intermediate messages (is_final=False) do NOT need metadata — only the final response needs `reply_to_created_date`.

### Step 3: Add reply_to_created_date to goconnect.py send()

File: `backend/app/channels/goconnect.py`, method `send()`

After building payload, add `reply_to_created_date` from metadata to first chunk only:

```python
for i, chunk in enumerate(self._split_text(text)):
    payload = {
        "type": "text",
        "text": chunk,
        "metadata": meta,
    }
    # Only first chunk carries reply-to (matches GoClaw behavior)
    if i == 0:
        reply_to = msg.metadata.get("message_created_date", "")
        if reply_to:
            payload["reply_to_created_date"] = reply_to
    # ... existing api_call ...
```

**Important:** Change `send()` to use `enumerate()` loop instead of plain `for chunk in ...`.

## Success Criteria

- [ ] OutboundMessage contains metadata from InboundMessage
- [ ] First outbound text chunk includes `reply_to_created_date` when `message_created_date` exists in metadata
- [ ] Subsequent chunks do NOT include `reply_to_created_date`
- [ ] Other channels (Slack, Telegram, Feishu) are not affected (they ignore unknown metadata keys)
