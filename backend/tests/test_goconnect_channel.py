"""Tests for GoConnect channel integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.channels.goconnect import _GOCONNECT_MAX_TEXT_LEN, GoConnectChannel
from app.channels.manager import CHANNEL_CAPABILITIES
from app.channels.message_bus import InboundMessageType, MessageBus, OutboundMessage, ResolvedAttachment
from app.channels.service import _CHANNEL_REGISTRY

pytestmark = pytest.mark.anyio


# -- fixtures --------------------------------------------------------------

def _make_channel(extra_config: dict | None = None) -> GoConnectChannel:
    bus = MessageBus()
    config = {
        "base_url": "http://chat-service:3000",
        "api_key": "test-api-key",
        "webhook_token": "test-token",
        "bot_user_id": "bot-uuid-123",
        "bot_user_code": "BOT_TEST",
    }
    if extra_config:
        config.update(extra_config)
    return GoConnectChannel(bus=bus, config=config)


def _make_outbound(chat_id: str = "room-1", text: str = "hello", **kwargs) -> OutboundMessage:
    return OutboundMessage(
        channel_name="goconnect",
        chat_id=chat_id,
        thread_id="thread-1",
        text=text,
        **kwargs,
    )


# -- registration tests ----------------------------------------------------

class TestGoConnectRegistration:
    def test_in_registry(self) -> None:
        assert "goconnect" in _CHANNEL_REGISTRY
        assert "GoConnectChannel" in _CHANNEL_REGISTRY["goconnect"]

    def test_capabilities(self) -> None:
        assert "goconnect" in CHANNEL_CAPABILITIES
        assert CHANNEL_CAPABILITIES["goconnect"]["supports_streaming"] is False


# -- init + lifecycle tests ------------------------------------------------

class TestGoConnectLifecycle:
    def test_init(self) -> None:
        ch = _make_channel()
        assert ch.name == "goconnect"
        assert ch._base_url == "http://chat-service:3000"
        assert ch._api_key == "test-api-key"

    async def test_start_stop(self) -> None:
        ch = _make_channel()
        await ch.start()
        assert ch.is_running
        assert ch._http_client is not None

        await ch.stop()
        assert not ch.is_running
        assert ch._http_client is None

    async def test_start_missing_base_url(self) -> None:
        ch = _make_channel({"base_url": ""})
        await ch.start()
        assert not ch.is_running

    async def test_start_missing_api_key(self) -> None:
        ch = _make_channel({"api_key": ""})
        await ch.start()
        assert not ch.is_running

    async def test_start_missing_bot_user_id(self) -> None:
        ch = _make_channel({"bot_user_id": ""})
        await ch.start()
        assert not ch.is_running


# -- webhook handler tests -------------------------------------------------

class TestGoConnectWebhook:
    async def test_valid_payload(self) -> None:
        ch = _make_channel()
        ch.bus.publish_inbound = AsyncMock()

        result = await ch.handle_webhook({
            "token": "test-token",
            "room_id": "room-1",
            "user_id": "user-1",
            "message": "hello bot",
            "user_name": "Test User",
            "message_created_date": "2026-04-16T09:00:00Z",
            "room_type": "group",
        })

        assert result["status"] == "accepted"
        ch.bus.publish_inbound.assert_called_once()
        inbound = ch.bus.publish_inbound.call_args[0][0]
        assert inbound.chat_id == "room-1"
        assert inbound.user_id == "user-1"
        assert inbound.text == "hello bot"
        assert inbound.topic_id == "room-1"
        assert inbound.msg_type == InboundMessageType.CHAT

    async def test_invalid_token(self) -> None:
        ch = _make_channel()
        result = await ch.handle_webhook({
            "token": "wrong-token",
            "room_id": "room-1",
            "user_id": "user-1",
            "message": "hello",
        })
        assert result["status"] == "error"
        assert "token" in result["message"]

    async def test_missing_required_fields(self) -> None:
        ch = _make_channel()
        result = await ch.handle_webhook({"token": "test-token", "room_id": "room-1"})
        assert result["status"] == "error"
        assert "missing" in result["message"]

    async def test_command_detection(self) -> None:
        ch = _make_channel()
        ch.bus.publish_inbound = AsyncMock()

        await ch.handle_webhook({
            "token": "test-token",
            "room_id": "room-1",
            "user_id": "user-1",
            "message": "/status",
        })

        inbound = ch.bus.publish_inbound.call_args[0][0]
        assert inbound.msg_type == InboundMessageType.COMMAND

    async def test_no_token_validation_when_unconfigured(self) -> None:
        ch = _make_channel({"webhook_token": ""})
        ch.bus.publish_inbound = AsyncMock()

        result = await ch.handle_webhook({
            "room_id": "room-1",
            "user_id": "user-1",
            "message": "hello",
        })
        assert result["status"] == "accepted"


# -- outbound send tests ---------------------------------------------------

class TestGoConnectSend:
    async def test_send_text_message(self) -> None:
        ch = _make_channel()
        ch._http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.content = b'{"success": true}'
        mock_resp.raise_for_status = MagicMock()
        ch._http_client.request = AsyncMock(return_value=mock_resp)

        msg = _make_outbound(text="test reply")
        await ch.send(msg)

        ch._http_client.request.assert_called_once()
        call_args = ch._http_client.request.call_args
        assert call_args[0][0] == "POST"
        assert "webhook/response" in call_args[0][1]
        payload = call_args[1]["json"]
        assert payload["text"] == "test reply"
        assert payload["metadata"]["room_id"] == "room-1"

    async def test_send_text_chunking(self) -> None:
        ch = _make_channel()
        ch._http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.content = b'{"success": true}'
        mock_resp.raise_for_status = MagicMock()
        ch._http_client.request = AsyncMock(return_value=mock_resp)

        long_text = "a" * (_GOCONNECT_MAX_TEXT_LEN + 100)
        msg = _make_outbound(text=long_text)
        await ch.send(msg)

        assert ch._http_client.request.call_count == 2

    async def test_send_includes_reply_to_created_date(self) -> None:
        """First chunk should include reply_to_created_date from metadata."""
        ch = _make_channel()
        ch._http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.content = b'{"success": true}'
        mock_resp.raise_for_status = MagicMock()
        ch._http_client.request = AsyncMock(return_value=mock_resp)

        msg = _make_outbound(
            text="reply text",
            metadata={"message_created_date": "2026-04-16T10:00:00.000Z", "bot_user_id": "bot-uuid-123", "bot_user_code": "BOT_TEST"},
        )
        await ch.send(msg)

        payload = ch._http_client.request.call_args[1]["json"]
        assert payload["reply_to_created_date"] == "2026-04-16T10:00:00.000Z"

    async def test_send_reply_to_only_first_chunk(self) -> None:
        """Only the first chunk should carry reply_to_created_date."""
        ch = _make_channel()
        ch._http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.content = b'{"success": true}'
        mock_resp.raise_for_status = MagicMock()
        ch._http_client.request = AsyncMock(return_value=mock_resp)

        long_text = "a" * (_GOCONNECT_MAX_TEXT_LEN + 100)
        msg = _make_outbound(
            text=long_text,
            metadata={"message_created_date": "2026-04-16T10:00:00.000Z"},
        )
        await ch.send(msg)

        assert ch._http_client.request.call_count == 2
        first_payload = ch._http_client.request.call_args_list[0][1]["json"]
        second_payload = ch._http_client.request.call_args_list[1][1]["json"]
        assert "reply_to_created_date" in first_payload
        assert "reply_to_created_date" not in second_payload

    async def test_send_without_reply_to(self) -> None:
        """No reply_to_created_date when metadata lacks message_created_date."""
        ch = _make_channel()
        ch._http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.content = b'{"success": true}'
        mock_resp.raise_for_status = MagicMock()
        ch._http_client.request = AsyncMock(return_value=mock_resp)

        msg = _make_outbound(text="reply text")
        await ch.send(msg)

        payload = ch._http_client.request.call_args[1]["json"]
        assert "reply_to_created_date" not in payload

    async def test_send_empty_skipped(self) -> None:
        ch = _make_channel()
        ch._http_client = AsyncMock(spec=httpx.AsyncClient)

        msg = _make_outbound(text="")
        await ch.send(msg)

        ch._http_client.request.assert_not_called()


# -- file upload tests -----------------------------------------------------

class TestGoConnectFileUpload:
    async def test_3step_flow(self, tmp_path: Path) -> None:
        test_file = tmp_path / "report.pdf"
        test_file.write_bytes(b"fake-pdf-content")

        ch = _make_channel()
        ch._http_client = AsyncMock(spec=httpx.AsyncClient)

        # Mock _api_call for init and commit
        init_response = b'{"success": true, "data": {"file_id": "f1", "object_key": "k1", "presigned_url": "https://s3.example.com/upload", "chat_content_id": "cc1"}}'
        commit_response = b'{"success": true}'

        ch._api_call = AsyncMock(side_effect=[init_response, commit_response])

        # Mock PUT to presigned URL
        put_resp = MagicMock()
        put_resp.raise_for_status = MagicMock()
        ch._http_client.put = AsyncMock(return_value=put_resp)

        attachment = ResolvedAttachment(
            virtual_path="/mnt/user-data/outputs/report.pdf",
            actual_path=test_file,
            filename="report.pdf",
            mime_type="application/pdf",
            size=16,
            is_image=False,
        )

        msg = _make_outbound()
        result = await ch.send_file(msg, attachment)

        assert result is True
        assert ch._api_call.call_count == 2
        ch._http_client.put.assert_called_once()

    async def test_init_failure(self, tmp_path: Path) -> None:
        test_file = tmp_path / "doc.txt"
        test_file.write_bytes(b"content")

        ch = _make_channel()
        ch._http_client = AsyncMock(spec=httpx.AsyncClient)
        ch._api_call = AsyncMock(side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock()))

        attachment = ResolvedAttachment(
            virtual_path="/mnt/user-data/outputs/doc.txt",
            actual_path=test_file,
            filename="doc.txt",
            mime_type="text/plain",
            size=7,
            is_image=False,
        )

        msg = _make_outbound()
        result = await ch.send_file(msg, attachment)

        assert result is False


# -- text splitting tests --------------------------------------------------

class TestGoConnectTextSplit:
    def test_short_text(self) -> None:
        assert GoConnectChannel._split_text("hello") == ["hello"]

    def test_empty_text(self) -> None:
        assert GoConnectChannel._split_text("") == []

    def test_long_text_splits(self) -> None:
        text = "a" * (_GOCONNECT_MAX_TEXT_LEN + 10)
        chunks = GoConnectChannel._split_text(text)
        assert len(chunks) == 2
        assert len(chunks[0]) == _GOCONNECT_MAX_TEXT_LEN

    def test_split_at_newline(self) -> None:
        # Build text with a newline near the boundary
        part1 = "a" * (_GOCONNECT_MAX_TEXT_LEN - 10)
        part2 = "b" * 20
        text = part1 + "\n" + part2
        chunks = GoConnectChannel._split_text(text)
        assert len(chunks) == 2
        assert chunks[0] == part1


# -- hooks alias routing tests ---------------------------------------------

class TestGoConnectHooksAlias:
    """Verify /hooks/goconnect endpoints are registered and delegate correctly."""

    def test_hooks_router_registered(self) -> None:
        from app.gateway.routers.channels import hooks_router

        paths = [route.path for route in hooks_router.routes]
        assert "/hooks/goconnect" in paths

    async def test_hooks_health(self) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.gateway.app import create_app

        test_app = create_app()
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/hooks/goconnect")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["channel"] == "goconnect"
