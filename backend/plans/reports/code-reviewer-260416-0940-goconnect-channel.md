# Code Review: GoConnect Channel Integration

**Branch:** goconnect-channel  
**Date:** 2026-04-16  
**Reviewer:** code-reviewer agent  
**Scope:** 6 files, ~300 LOC thay doi

---

## Scope

| File | Mo ta |
|------|-------|
| `app/channels/goconnect.py` | GoConnectChannel class (moi) |
| `app/channels/service.py` | +1 dong: dang ky "goconnect" |
| `app/channels/manager.py` | +1 dong: capabilities |
| `app/gateway/routers/channels.py` | POST/GET webhook endpoints |
| `tests/test_goconnect_channel.py` | 21 unit tests (moi) |
| `config.example.yaml` | Config mau |

---

## Overall Assessment

Implementation sach, dung pattern Channel hien co. Tich hop chinh xac voi MessageBus, `_CHANNEL_REGISTRY`, `CHANNEL_CAPABILITIES`. Logic file upload 3-step ro rang. Tests phu du cac happy path va failure cases quan trong.

Co **1 van de bao mat trung binh** (HTTP 200 khi token sai), **2 bug logic nho**, va mot so diem informational.

---

## Critical Issues

_Khong co._

---

## High Priority

### [HIGH-1] Token mismatch tra ve HTTP 200 thay vi 401

**File:** `app/gateway/routers/channels.py:55` + `app/channels/goconnect.py:78-82`

`handle_webhook()` tra ve dict `{"status": "error", "message": "invalid webhook token"}`. Router `return result` (line 55) nen HTTP response la **200 OK** du token sai.

**Tac dong:** GoConnect Chat Service co the bi nham la "webhook thanh cong" vi nhan 200, dan den no khong retry hay bao loi. Cac client scanner khong phan biet duoc endpoint co xac thuc hay khong.

**Fix de xuat:**
```python
# routers/channels.py
result = await channel.handle_webhook(payload)
if result.get("status") == "error":
    raise HTTPException(status_code=401, detail=result.get("message", "Unauthorized"))
return result
```

---

## Medium Priority

### [MED-1] `import json` nam trong than ham

**File:** `app/channels/goconnect.py:183`

```python
try:
    import json  # <- nam giua ham send_file()
    init_resp = json.loads(init_resp_bytes)
```

`json` la stdlib, khong co ly do gi de lazy import. Nen dua len top-level.

**Fix:** Move `import json` len dau file cung cac import khac.

### [MED-2] `_split_text("")` tra ve `[""]` -- gui text rong toi API

**File:** `app/channels/goconnect.py:258-259`

```python
if not text:
    return [""]  # Nen la []
```

`send()` da check `if not text: return` truoc nen `_split_text("")` khong bao gio duoc goi tu `send()`. Tuy nhien neu ai goi truc tiep thi se gui API call voi `{"text": ""}` -- lang phi.

**Fix:**
```python
if not text:
    return []
```

---

## Low Priority (Non-blocking)

### [LOW-1] `read_bytes()` khong duoc wrap trong try/except trong `send_file()`

**File:** `app/channels/goconnect.py:155`

Neu file bi xoa giua resolve va upload, `OSError` propagates len `_on_outbound` (base class catch it). Khong crash, nhung log message khong ro rang. Nen wrap rieng:

```python
try:
    file_data = attachment.actual_path.read_bytes()
except OSError:
    logger.exception("[GoConnect] failed to read file: %s", attachment.filename)
    return False
```

### [LOW-2] Khong co test cho `send_file()` khi `room_id` rong

`send_file()` tra ve `False` ngay khi `room_id` rong (line 151-153). Chua co test cover case nay.

### [LOW-3] Webhook endpoint khong khai bao response model

**File:** `app/gateway/routers/channels.py:37`

```python
@router.post("/goconnect/webhook")
async def goconnect_webhook(request: Request) -> dict:
```

Cac endpoint khac dung Pydantic response model. Nen them `GoConnectWebhookResponse(BaseModel)` de consistency va OpenAPI docs day du.

### [LOW-4] Empty file upload (0 bytes) chua duoc test/guard

**File:** `app/channels/goconnect.py:165`

Neu file 0 bytes: `chunk_size = 0`, `initial_chunk = ""`. API co the tu choi. Nen add guard hoac test voi file 0 bytes.

### [LOW-5] Plain string comparison cho webhook_token -- co the dung `hmac.compare_digest`

**File:** `app/channels/goconnect.py:79`

```python
if self._webhook_token and token != self._webhook_token:
```

Timing attack vector. Voi internal webhook (khong public internet) rui ro thap -- da chap nhan theo design decision. Neu endpoint expose public, nen dung `hmac.compare_digest(token, self._webhook_token)`.

---

## Edge Cases Found by Scout

1. **Presigned URL:** Den tu internal goclaw-connector (trusted) -- khong phai SSRF risk.
2. **Concurrent file uploads:** `httpx.AsyncClient` la async-safe cho concurrent requests -- OK.
3. **`stop()` trong khi `send_file()` dang chay:** HTTP client se bi close, PUT raise exception, duoc catch boi `_on_outbound` -- acceptable.
4. **`restart_channel` endpoint `/{name}/restart`:** `name` duoc validate qua `_CHANNEL_REGISTRY.get(name)` trong service -- khong co injection risk.
5. **`metadata` rong tren OutboundMessage:** Default `{}` tu dataclass, fallback ve `self._bot_user_id` hoat dong dung -- OK.

---

## Positive Observations

- Pattern nhat quan voi Slack/Telegram (same `_make_inbound`, `topic_id`, `_on_outbound`).
- `start()` check ca 3 required config fields truoc khi init HTTP client.
- `_split_text` uu tien split tai newline, fallback hard split.
- `send_file()` tra ve `bool` dung convention `Channel.send_file()`.
- `stop()` clean: unsubscribe outbound, close HTTP client, set `_running = False`.
- Tests phu tot: lifecycle, webhook auth, text chunking, file upload happy/sad paths.
- Config example day du voi env var placeholders.

---

## Recommended Actions

| Priority | Action |
|----------|--------|
| HIGH | Fix HTTP 200 -> 401 khi token mismatch trong `goconnect_webhook` |
| MEDIUM | Move `import json` len top-level |
| MEDIUM | Fix `_split_text("")` tra ve `[]` thay vi `[""]` |
| LOW | Wrap `read_bytes()` trong try/except |
| LOW | Them guard/test cho empty file upload |
| LOW | Them Pydantic response model cho webhook endpoint |

---

## Metrics

- Tests: 21 tests, phu lifecycle, webhook auth, send, file upload, text split
- Linting: 0 loi
- Type annotations: day du, nhat quan

---

## Unresolved Questions

1. GoConnect Chat Service co expect HTTP 401 khi token sai, hay chi check body `status: error`? Neu khong quan tam HTTP status thi [HIGH-1] downgrade xuong MEDIUM.
2. `initial_chunk` trong file-init API dung de lam gi chinh xac (MIME detection hay pre-upload)? File rong (`initial_chunk: ""`) can test voi real API.
3. Endpoint co expose public internet khong? Neu co, can rate limiting va nen dung `hmac.compare_digest`.

