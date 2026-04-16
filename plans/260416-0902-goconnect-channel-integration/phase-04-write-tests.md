---
phase: 4
title: "Write Tests"
status: done
effort: "~120 LOC"
---

# Phase 4: Write Tests

## Overview

Unit tests for GoConnect channel: webhook handling, outbound send, file upload, registration.

## Related Code Files

- **Create:** `backend/tests/test_goconnect_channel.py`
- **Read:** `backend/tests/` (existing patterns)

## Implementation Steps

### 1. Test webhook handling

```python
class TestGoConnectWebhook:
    async def test_valid_webhook_payload(self):
        """Valid payload → accepted, inbound published to bus."""

    async def test_invalid_token(self):
        """Wrong webhook_token → rejected."""

    async def test_missing_required_fields(self):
        """Missing room_id/user_id/message → error."""

    async def test_command_detection(self):
        """Message starting with / → InboundMessageType.COMMAND."""
```

### 2. Test outbound send

```python
class TestGoConnectSend:
    async def test_send_text_message(self):
        """Text → POST /webhook/response with correct payload."""

    async def test_send_text_chunking(self):
        """Long text (>5000 chars) → multiple API calls."""

    async def test_send_empty_skipped(self):
        """Empty text + no attachments → no API call."""
```

### 3. Test file upload

```python
class TestGoConnectFileUpload:
    async def test_3step_flow(self):
        """file-init → PUT → file-commit sequence."""

    async def test_init_failure(self):
        """file-init fails → send_file returns False."""
```

### 4. Test registration

```python
class TestGoConnectRegistration:
    def test_in_registry(self):
        """goconnect in _CHANNEL_REGISTRY."""

    def test_capabilities(self):
        """goconnect in CHANNEL_CAPABILITIES, supports_streaming=False."""
```

### Test approach

- Mock `httpx.AsyncClient` for outbound API calls
- Mock `MessageBus` for inbound publish verification
- No real GoConnect Chat Service needed
- Follow existing patterns in `backend/tests/`

## Success Criteria

- [ ] `test_goconnect_channel.py` created
- [ ] All tests pass: `PYTHONPATH=. uv run pytest tests/test_goconnect_channel.py -v`
- [ ] Webhook auth, text send, file upload, registration covered
