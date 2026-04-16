---
title: "Fix GoConnect Webhook Compatibility"
description: "Fix reply_to_created_date missing + add /hooks/goconnect alias path for GoClaw compatibility"
status: completed
priority: P1
created: 2026-04-16
blockedBy: []
blocks: []
---

# Fix GoConnect Webhook Compatibility

## Overview

Brainstorm compatibility check revealed DeerFlow GoConnect webhook missing `reply_to_created_date` in outbound responses — Chat Service can't thread-reply, responses appear as floating messages. Also add `/hooks/goconnect` alias (GoClaw convention) while keeping existing `/api/channels/goconnect/webhook`.

**Reference:** GoClaw implementation at `/Users/hieutv/Documents/workspace/hieutv-dng@github.com/goclaw/internal/channels/goconnect/`

## Phases

| Phase | Name | Status | Effort |
|-------|------|--------|--------|
| 1 | [Fix reply_to_created_date](./phase-01-fix-reply-to-created-date.md) | Done | ~15 LOC |
| 2 | [Add /hooks/goconnect Alias](./phase-02-add-hooks-goconnect-alias.md) | Done | ~25 LOC |
| 3 | [Update Tests](./phase-03-update-tests.md) | Done | ~30 LOC |

**Total estimate:** ~70 LOC changes

## Dependencies

Follow-up fix for `260416-0902-goconnect-channel-integration` (done).

## Validation Log

### Verification Results
- **Tier:** Standard (Fact Checker + Contract Verifier)
- **Claims checked:** 19
- **Verified:** 19 | **Failed:** 0 | **Unverified:** 0

### Session 1 — 2026-04-16
**Trigger:** `/ck:plan validate` before implementation
**Questions asked:** 3

#### Questions & Answers

1. **[Assumptions]** Plan truyền toàn bộ `msg.metadata` dict (room_id, user_id, user_name, bot_user_id, bot_user_code, message_created_date, room_type) từ InboundMessage sang OutboundMessage cho TẤT CẢ channels. Bạn muốn xử lý thế nào?
   - Options: Truyền toàn bộ metadata (Recommended) | Chỉ truyền message_created_date | Filter theo channel_name
   - **Answer:** Truyền toàn bộ metadata
   - **Rationale:** Đơn giản, đúng pattern — metadata là generic dict, channels khác tự bỏ qua keys không liên quan.

2. **[Architecture]** Plan đặt `/hooks/goconnect` NGOÀI namespace `/api/`. Path `/hooks/` sẽ không inherit middleware/auth nào từ `/api/`. Confirm approach?
   - Options: /hooks/goconnect (Recommended) | /api/hooks/goconnect
   - **Answer:** /hooks/goconnect
   - **Rationale:** Đúng convention GoClaw. Webhook auth dùng token trong payload (đã có), không phụ thuộc path-level middleware.

3. **[Tradeoffs]** Hiện tại `send()` luôn dùng config values cho bot_user_id/bot_user_code (vì metadata rỗng). Sau fix, inbound payload values sẽ ưu tiên hơn config. Đây là behavior change — giữ logic nào?
   - Options: Ưu tiên inbound payload (Recommended) | Luôn dùng config values
   - **Answer:** Ưu tiên inbound payload
   - **Rationale:** Inbound payload có thể mang bot identity khác (multi-bot). Fallback config vẫn hoạt động khi payload thiếu.

#### Confirmed Decisions
- Metadata propagation: full dict pass-through — YAGNI, không filter
- Hooks path: `/hooks/goconnect` ngoài `/api/` — đúng GoClaw convention
- Bot identity: ưu tiên inbound payload, fallback config — hỗ trợ multi-bot

#### Action Items
- None — plan không cần thay đổi

#### Impact on Phases
- Không thay đổi — tất cả decisions align với plan hiện tại
