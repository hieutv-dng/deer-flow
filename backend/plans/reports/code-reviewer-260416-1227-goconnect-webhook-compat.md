# Code Review: GoConnect Webhook Compatibility Fix

**Branch:** goconnect-channel  
**Files changed:** 6 (goconnect.py, manager.py, channels.py, app.py, nginx.conf, test_goconnect_channel.py)  
**Tests:** 26 passed / 0 failed (full suite: 1945 passed)

---

## Overall Assessment

Thay đổi nhỏ, rõ ràng, đúng mục đích. Logic cốt lõi đúng, test coverage tốt (5 test mới cover đủ các nhánh). Không có breaking change. Một số điểm cần chú ý về bảo mật metadata và một edge case về routing.

---

## Critical Issues

Không có.

---

## High Priority

### 1. Metadata pass-through không lọc — rủi ro rò rỉ dữ liệu nội bộ

**File:** `app/channels/manager.py` (dòng 764, 870)

`metadata=msg.metadata` truyền toàn bộ dict từ inbound GoConnect webhook thẳng vào `OutboundMessage`. Dict này bao gồm: `user_id`, `user_name`, `room_id`, `room_type`, `bot_user_id`, `bot_user_code`, `message_created_date`.

Vấn đề: `metadata` của `OutboundMessage` được các channel khác cũng đọc (ví dụ `WechatChannel` đọc `metadata.get("context_token")`). Nếu một kênh khác lỡ cài `_on_outbound` callback và nhận được `msg.channel_name != self.name` (đã được lọc đúng ở `base.py:95`) thì không bị lọc sai. **Routing đúng.**

Tuy nhiên, điều quan trọng hơn: `GoConnectChannel.send()` đọc `msg.metadata.get("bot_user_id", self._bot_user_id)` để build payload gửi lên GoClaw. Nếu caller nào đó tạo `OutboundMessage` với `metadata` giả mạo `bot_user_id`, có thể spoof identity khi gọi API. Trong flow hiện tại thì `OutboundMessage` chỉ được tạo bởi `ChannelManager` (code nội bộ) nên không có attack vector từ ngoài. Tuy nhiên, đây là **design risk tiềm ẩn** nếu sau này thêm API endpoint tạo outbound thủ công.

**Recommendation:** Không cần sửa ngay, nhưng nên document rõ trong docstring của `GoConnectChannel.send()` rằng `bot_user_id` trong metadata có thể override config — tức là trust boundary của field này là internal-only.

---

## Medium Priority

### 2. `/hooks/goconnect` — thiếu kiểm tra webhook token khi unauthenticated request qua path mới

**File:** `app/gateway/routers/channels.py`

`goconnect_hooks_webhook` delegate hoàn toàn sang `goconnect_webhook` — token validation vẫn hoạt động đúng bên trong `GoConnectChannel.handle_webhook()`. Không có vấn đề bảo mật thực sự ở đây.

Tuy nhiên: hai endpoint `/api/channels/goconnect/webhook` (POST) và `/hooks/goconnect` (POST) đều public, không có rate-limiting ở FastAPI layer (chỉ có ở nginx nếu được cấu hình). Nếu GoClaw gửi burst request lớn, cả hai path đều đến cùng handler và cùng semaphore của `ChannelManager` (max_concurrency=5), nên không bị overflow. OK.

### 3. `hooks_router` không có openapi tag "channels"

**File:** `app/gateway/routers/channels.py`

`hooks_router` dùng tag `"hooks"` nhưng tag này không được khai báo trong `app.py` `openapi_tags`. Swagger UI sẽ hiển thị tab "hooks" không có description. Không ảnh hưởng chức năng.

**Fix:** Thêm vào `openapi_tags` trong `app.py`:
```python
{"name": "hooks", "description": "Webhook aliases for external platform conventions (GoClaw)"},
```

hoặc reuse tag `"channels"` trên `hooks_router` để gộp chung.

### 4. `_split_text` có thể trả về chunk rỗng trong edge case cụ thể

**File:** `app/channels/goconnect.py`, `_split_text()`

Khi `split_at <= _GOCONNECT_MAX_TEXT_LEN // 4` (không tìm được newline gần boundary), code fallback sang `split_at = _GOCONNECT_MAX_TEXT_LEN`. Sau đó `remaining = remaining[split_at:].lstrip("\n")`. Nếu `remaining[split_at:]` là toàn `\n`, `lstrip` sẽ trả về chuỗi rỗng, và `if remaining: chunks.append(remaining)` sẽ bỏ qua — đúng. OK.

Nhưng chunk đầu (dòng `chunks.append(remaining[:split_at])`) có thể là chuỗi rỗng nếu `split_at == 0` — điều này không xảy ra vì `split_at` luôn >= `_GOCONNECT_MAX_TEXT_LEN // 4 + 1` hoặc `_GOCONNECT_MAX_TEXT_LEN`. Không phải bug.

---

## Low Priority

### 5. Intermediate streaming chunk thiếu metadata

**File:** `app/channels/manager.py` (~dòng 818-829)

Intermediate streaming `OutboundMessage` (is_final=False) không có `metadata`. Với GoConnect (supports_streaming=False), điều này không ảnh hưởng. Nhưng nếu sau này GoConnect được enable streaming, các chunk trung gian sẽ thiếu `message_created_date` → `reply_to_created_date` sẽ không được gửi kèm. Không phải bug hiện tại nhưng là technical debt.

### 6. Test `test_hooks_health` spin up full app — hơi nặng

**File:** `tests/test_goconnect_channel.py`

`create_app()` trong test tạo full FastAPI app với lifespan events. Test dùng `ASGITransport` nên lifespan không được trigger — an toàn. Nhưng nếu sau này cần test POST `/hooks/goconnect` đầy đủ (cần channel service), sẽ cần mock phức tạp hơn. Cân nhắc thêm test cho POST path với mock service.

---

## Positive Observations

- Logic `enumerate()` để chỉ set `reply_to_created_date` ở chunk đầu: đơn giản, đúng, không side effect.
- `metadata=msg.metadata` được thêm ở cả non-streaming (dòng 764) và streaming final (dòng 870) — symmetric và đúng.
- Token validation logic trong `handle_webhook` không thay đổi — không có regression.
- Nginx `location /hooks/` được đặt đúng vị trí (trước `location /`), timeout 600s nhất quán với `/api/channels/`.
- 26 test cases pass sạch, không flaky.
- `_make_outbound()` fixture có `**kwargs` nên dễ extend metadata trong test.

---

## Checklist Kết Quả

| Mục | Kết quả |
|-----|---------|
| Concurrency | OK — không thay đổi semaphore logic |
| Error boundaries | OK — exception handling không thay đổi |
| API contracts | OK — OutboundMessage.metadata field đã có sẵn, không breaking |
| Backwards compat | OK — /api/channels/goconnect/webhook không đổi |
| Input validation | OK — token validation vẫn trong GoConnectChannel.handle_webhook |
| Auth/authz | OK — cả hai path đều qua cùng token check |
| N+1 / query | N/A |
| Data leaks | Thấp — metadata nội bộ không lộ ra ngoài qua HTTP response |
| Fact-checked | Đã grep-verify tất cả file paths và symbol names |

---

## Unresolved Questions

1. GoClaw có yêu cầu `reply_to_created_date` là ISO8601 strict format không? Hiện tại code chỉ pass-through string từ webhook, không validate format.
2. Có timeout retry nào từ phía GoClaw không? Nếu `/hooks/goconnect` trả về `202 Accepted` ngay và xử lý async thì latency 600s sẽ không là vấn đề, nhưng hiện tại response là sync — có risk timeout ở GoClaw side nếu LLM inference chậm.
