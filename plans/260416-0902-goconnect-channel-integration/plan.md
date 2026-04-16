---
title: "Tích hợp GoConnect Channel vào DeerFlow"
description: "Port GoConnect channel từ goclaw (Go) sang deer-flow (Python). Webhook inbound + REST API outbound."
status: done
priority: P1
created: 2026-04-16
source: brainstorm-260416-goconnect
---

# Tích hợp GoConnect Channel vào DeerFlow

## Overview

Port GoConnect channel integration từ goclaw project (Go) sang DeerFlow (Python). GoConnect là messaging platform nội bộ VNPT, dùng webhook-based inbound và REST API outbound.

**Key facts:**
- Inbound: Chat Service POST webhook khi user @mention bot
- Outbound: REST API tới goclaw-connector (text + 3-step file upload)
- Auth: `api-key` header (outbound) + shared `webhook_token` (inbound)
- Message ID: `created_date` (ISO 8601), không phải integer
- Đây là channel đầu tiên trong DeerFlow cần webhook endpoint

**Reference:** `/Users/hieutv/Documents/workspace/hieutv-dng@github.com/goclaw/internal/channels/goconnect/`

## Phases

| Phase | Name | Status | Effort |
|-------|------|--------|--------|
| 1 | [Implement GoConnect Channel](./phase-01-implement-goconnect-channel.md) | Done | ~180 LOC |
| 2 | [Register & Configure](./phase-02-register-configure.md) | Done | ~20 LOC |
| 3 | [Add Webhook Route](./phase-03-add-webhook-route.md) | Done | ~40 LOC |
| 4 | [Write Tests](./phase-04-write-tests.md) | Done | ~120 LOC |

**Total estimate:** ~360 LOC changes

## Architecture

```
GoConnect Chat Service
        │ POST /api/channels/goconnect/webhook
        ▼
┌─────────────────────┐     ┌──────────────────┐
│ Gateway FastAPI      │────▶│ GoConnectChannel  │
│ routers/channels.py  │     │ handle_webhook()  │
└─────────────────────┘     │ _make_inbound()   │
                            └────────┬─────────┘
                                     │ MessageBus
                                     ▼
                            ┌──────────────────┐
                            │ ChannelManager    │
                            │ runs.wait()       │
                            └────────┬─────────┘
                                     │ OutboundMessage
                                     ▼
                            ┌──────────────────┐
                            │ GoConnectChannel  │
                            │ .send() → REST API│
                            │ .send_file() → 3-step│
                            └──────────────────┘
```

## NOT porting (YAGNI)

- Reaction system (DeerFlow has no reaction dispatch)
- Group history/compaction (DeerFlow uses thread + summarization)
- DM/Group policy (simplify to `allowed_users` like Telegram)
- Factory pattern (DeerFlow uses config.yaml, not DB)
- Contact collector (DeerFlow has no contact system)
- `markdownToGoConnect()` (GoConnect handles raw text fine, minimal conversion needed)

## Dependencies

None — independent feature, no cross-plan dependencies.

## Validation Log

### Verification Results
- **Tier:** Standard (Fact Checker + Contract Verifier)
- **Claims checked:** 20
- **Verified:** 19 | **Failed:** 1 (partial) | **Unverified:** 0
- **Failure:** Claim #16 — Constructor description says `(name, bus, config)` but code skeleton already correct `(bus, config)`. No action needed.

### Session 1 — 2026-04-16
**Trigger:** Pre-implementation validation
**Questions asked:** 6

#### Questions & Answers

1. **[Scope]** Plan port 3-step presigned URL file upload (~40 LOC trong send_file). File upload có cần cho MVP hay defer sang phase sau?
   - Options: Include MVP (Recommended) | Defer file upload | Text-only permanently
   - **Answer:** Include MVP
   - **Rationale:** GoConnect users thường share file qua bot, thiếu sẽ gây UX kém.

2. **[Architecture]** Plan map topic_id = room_id, nghĩa là mỗi GoConnect room = 1 DeerFlow thread duy nhất. Có đúng intent không?
   - Options: 1 room = 1 thread (Recommended) | Reset per session | Per-message thread
   - **Answer:** 1 room = 1 thread
   - **Rationale:** Đơn giản, phù hợp GoConnect rooms 1:1 bot conversation. DeerFlow summarization handle context dài.

3. **[Assumptions]** Plan skip markdownToGoConnect(). DeerFlow LLM output chứa markdown. GoConnect Chat Service render markdown hay hiển thị raw?
   - Options: Skip, raw text OK (Recommended) | Minimal strip | Full converter
   - **Answer:** Skip, raw text OK
   - **Rationale:** GoConnect Chat Service hỗ trợ markdown rendering cơ bản. Không cần converter.

4. **[Security]** Đây là webhook channel đầu tiên trong DeerFlow. Có cần thêm bảo mật nào ngoài webhook_token?
   - Options: Token-only (Recommended) | Token + IP whitelist | Token + rate limit | Token + IP + rate limit
   - **Answer:** Token-only
   - **Rationale:** Shared webhook_token đủ cho internal VNPT network. Giữ đơn giản, thêm sau nếu cần.

5. **[Access]** GoConnect Bot có cần filter allowed_users hay accept tất cả users trong room?
   - Options: Accept all (Recommended) | Config allowed_users | Config allowed_rooms
   - **Answer:** Accept all
   - **Rationale:** GoConnect rooms đã được quản lý bởi Chat Service admin. Ai đã ở trong room = được phép dùng bot.

6. **[Resilience]** Outbound API fail. Xử lý thế nào?
   - Options: Log & drop (Recommended) | Simple retry (3x) | Port goclaw retry
   - **Answer:** Log & drop
   - **Rationale:** Đơn giản, consistent với các channels khác (Discord, Telegram đều không retry).

#### Confirmed Decisions
- File upload: Include in MVP — port full 3-step flow
- Thread mapping: 1 room = 1 thread via `topic_id = room_id`
- Markdown: Skip converter, send raw markdown
- Security: Token-only validation
- Access control: Accept all users in room, no filtering
- Error handling: Log & drop, no retry

#### Action Items
- [x] All decisions align with existing plan — no phase changes needed

#### Impact on Phases
- Phase 1: No changes — plan already includes send_file() and topic_id=room_id
- Phase 2: No changes
- Phase 3: No changes
- Phase 4: No changes — test error handling as log & drop
