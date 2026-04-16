"""GoConnect channel integration — VNPT internal messaging platform.

Inbound: Chat Service POST webhook when user @mentions bot.
Outbound: REST API to goclaw-connector (text + 3-step file upload).
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from app.channels.base import Channel
from app.channels.message_bus import InboundMessageType, MessageBus, OutboundMessage, ResolvedAttachment

logger = logging.getLogger(__name__)

_GOCONNECT_MAX_TEXT_LEN = 5000
_CONNECTOR_BASE_PATH = "/api/v1/chatservice/goclaw-connector"


class GoConnectChannel(Channel):
    """GoConnect bot channel (webhook inbound + REST API outbound).

    Configuration keys (in ``config.yaml`` under ``channels.goconnect``):
        - ``base_url``: Chat Service URL (goclaw-connector).
        - ``api_key``: licenseKey for WebHookGuard auth.
        - ``webhook_token``: Shared secret for inbound webhook validation.
        - ``bot_user_id``: UUID of bot user on GoConnect.
        - ``bot_user_code``: Convention code (e.g. BOT_DEER_FLOW).
    """

    def __init__(self, bus: MessageBus, config: dict[str, Any]) -> None:
        super().__init__(name="goconnect", bus=bus, config=config)
        self._base_url = str(config.get("base_url", "")).rstrip("/")
        self._api_key = str(config.get("api_key", ""))
        self._webhook_token = str(config.get("webhook_token", ""))
        self._bot_user_id = str(config.get("bot_user_id", ""))
        self._bot_user_code = str(config.get("bot_user_code", ""))
        self._http_client: httpx.AsyncClient | None = None

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return

        if not self._base_url:
            logger.error("GoConnect channel requires base_url")
            return
        if not self._api_key:
            logger.error("GoConnect channel requires api_key")
            return
        if not self._bot_user_id:
            logger.error("GoConnect channel requires bot_user_id")
            return

        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._running = True
        self.bus.subscribe_outbound(self._on_outbound)
        logger.info("GoConnect channel started (base_url=%s, bot=%s)", self._base_url, self._bot_user_code)

    async def stop(self) -> None:
        self._running = False
        self.bus.unsubscribe_outbound(self._on_outbound)
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        logger.info("GoConnect channel stopped")

    # -- webhook handler ---------------------------------------------------

    async def handle_webhook(self, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, str]:
        """Process inbound webhook from GoConnect Chat Service.

        Token is accepted from ``Authorization: Bearer <token>`` header
        (GoClaw convention) or from the ``token`` field in the JSON body.
        """
        # Validate token — prefer Authorization header, fall back to body field
        token = ""
        if headers:
            auth = headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        if not token:
            token = payload.get("token", "")
        if self._webhook_token and token != self._webhook_token:
            logger.warning("[GoConnect] webhook token mismatch")
            return {"status": "error", "message": "invalid webhook token"}

        # Validate required fields
        room_id = payload.get("room_id", "")
        user_id = payload.get("user_id", "")
        message = payload.get("message", "")
        if not room_id or not user_id or not message:
            return {"status": "error", "message": "missing required fields: room_id, user_id, message"}

        # Determine message type
        msg_type = InboundMessageType.COMMAND if message.startswith("/") else InboundMessageType.CHAT

        # Build inbound message
        inbound = self._make_inbound(
            chat_id=room_id,
            user_id=user_id,
            text=message,
            msg_type=msg_type,
            metadata={
                "room_id": room_id,
                "user_id": user_id,
                "user_name": payload.get("user_name", ""),
                "bot_user_id": payload.get("bot_user_id", self._bot_user_id),
                "bot_user_code": payload.get("bot_user_code", self._bot_user_code),
                "message_created_date": payload.get("message_created_date", ""),
                "room_type": payload.get("room_type", ""),
            },
        )
        # Map room_id as topic_id so same room reuses same DeerFlow thread
        inbound.topic_id = room_id

        await self.bus.publish_inbound(inbound)
        return {"status": "accepted"}

    # -- outbound send -----------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        room_id = msg.chat_id
        if not room_id:
            logger.error("[GoConnect] missing room_id (chat_id) for outbound")
            return

        text = msg.text or ""
        if not text and not msg.attachments:
            return

        if not text:
            return

        meta = {
            "room_id": room_id,
            "bot_user_id": msg.metadata.get("bot_user_id", self._bot_user_id),
            "bot_user_code": msg.metadata.get("bot_user_code", self._bot_user_code),
        }

        # Chunk text if exceeds limit — only first chunk carries reply_to_created_date (GoClaw convention)
        for i, chunk in enumerate(self._split_text(text)):
            payload: dict[str, Any] = {
                "type": "text",
                "text": chunk,
                "metadata": meta,
            }
            if i == 0:
                reply_to = msg.metadata.get("message_created_date", "")
                if reply_to:
                    payload["reply_to_created_date"] = reply_to
            try:
                await self._api_call("POST", f"{_CONNECTOR_BASE_PATH}/webhook/response", payload)
            except Exception:
                logger.exception("[GoConnect] failed to send text chunk to room=%s", room_id)

    # -- file upload (3-step presigned URL) --------------------------------

    async def send_file(self, msg: OutboundMessage, attachment: ResolvedAttachment) -> bool:
        room_id = msg.chat_id
        if not room_id:
            return False

        file_data = attachment.actual_path.read_bytes()
        file_name = attachment.filename
        mime_type = attachment.mime_type

        bot_meta = {
            "bot_user_id": msg.metadata.get("bot_user_id", self._bot_user_id),
            "bot_user_code": msg.metadata.get("bot_user_code", self._bot_user_code),
        }

        # Step 1: file-init — get presigned URL
        chunk_size = min(256, len(file_data))
        initial_chunk = base64.b64encode(file_data[:chunk_size]).decode()

        init_payload = {
            "room_id": room_id,
            "file_name": file_name,
            "file_size": len(file_data),
            "content_type": mime_type,
            "initial_chunk": initial_chunk,
            "metadata": bot_meta,
        }

        try:
            init_resp_bytes = await self._api_call("POST", f"{_CONNECTOR_BASE_PATH}/webhook/file-init", init_payload)
        except Exception:
            logger.exception("[GoConnect] file-init failed for %s", file_name)
            return False

        try:
            init_resp = json.loads(init_resp_bytes)
        except (json.JSONDecodeError, TypeError):
            logger.error("[GoConnect] invalid file-init response for %s", file_name)
            return False

        if not init_resp.get("success"):
            logger.warning("[GoConnect] file-init rejected: %s", init_resp.get("message"))
            return False

        data = init_resp.get("data", {})
        presigned_url = data.get("presigned_url", "")
        file_id = data.get("file_id", "")
        object_key = data.get("object_key", "")
        chat_content_id = data.get("chat_content_id", "")

        if not presigned_url:
            logger.error("[GoConnect] no presigned_url in file-init response")
            return False

        # Step 2: PUT binary to presigned URL
        try:
            if not self._http_client:
                return False
            put_resp = await self._http_client.put(
                presigned_url,
                content=file_data,
                headers={"Content-Type": mime_type},
            )
            put_resp.raise_for_status()
        except Exception:
            logger.exception("[GoConnect] file PUT failed for %s", file_name)
            return False

        # Step 3: file-commit
        commit_payload = {
            "room_id": room_id,
            "file_id": file_id,
            "object_key": object_key,
            "expected_size": len(file_data),
            "file_name": file_name,
            "content_type": mime_type,
            "message": msg.text or "",
            "chat_content_id": chat_content_id,
            "metadata": bot_meta,
        }

        try:
            await self._api_call("POST", f"{_CONNECTOR_BASE_PATH}/webhook/file-commit", commit_payload)
        except Exception:
            logger.exception("[GoConnect] file-commit failed for %s", file_name)
            return False

        logger.info("[GoConnect] file uploaded: %s (%d bytes)", file_name, len(file_data))
        return True

    # -- helpers -----------------------------------------------------------

    async def _api_call(self, method: str, path: str, payload: dict | None = None) -> bytes:
        """Make authenticated REST API call to Chat Service."""
        if not self._http_client:
            raise RuntimeError("GoConnect HTTP client not initialized")

        url = self._base_url + path
        headers = {"api-key": self._api_key, "Content-Type": "application/json"}

        resp = await self._http_client.request(method, url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.content

    @staticmethod
    def _split_text(text: str) -> list[str]:
        """Split text into chunks respecting newline boundaries."""
        if not text:
            return []

        if len(text) <= _GOCONNECT_MAX_TEXT_LEN:
            return [text]

        chunks: list[str] = []
        remaining = text
        while len(remaining) > _GOCONNECT_MAX_TEXT_LEN:
            split_at = remaining.rfind("\n", 0, _GOCONNECT_MAX_TEXT_LEN)
            if split_at <= _GOCONNECT_MAX_TEXT_LEN // 4:
                split_at = _GOCONNECT_MAX_TEXT_LEN
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")

        if remaining:
            chunks.append(remaining)

        return chunks
