---
phase: 3
title: "Update Tests"
status: completed
effort: "~30 LOC"
priority: MEDIUM
---

# Phase 3: Update Tests

## Overview

Update existing test suite `backend/tests/test_goconnect_channel.py` to verify reply_to_created_date behavior and hooks alias routing.

## Related Code Files

Files to modify:
- `backend/tests/test_goconnect_channel.py` — add test cases

## Implementation Steps

### Step 1: Test reply_to_created_date in send()

Add test: `test_send_includes_reply_to_created_date`
- Create OutboundMessage with `metadata={"message_created_date": "2026-04-16T10:00:00.000Z"}`
- Call `channel.send(msg)`
- Assert first API call payload contains `reply_to_created_date`
- If multiple chunks, assert only first has `reply_to_created_date`

### Step 2: Test send() without reply_to

Add test: `test_send_without_reply_to`
- Create OutboundMessage with empty metadata
- Assert payload does NOT contain `reply_to_created_date`

### Step 3: Test hooks alias endpoints

Add test: verify `/hooks/goconnect` POST and GET work via FastAPI TestClient.

## Success Criteria

- [ ] All existing 21 tests still pass
- [ ] New tests for reply_to_created_date pass
- [ ] `make test` passes in backend directory
