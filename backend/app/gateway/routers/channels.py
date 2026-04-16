"""Gateway router for IM channel management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelStatusResponse(BaseModel):
    service_running: bool
    channels: dict[str, dict]


class ChannelRestartResponse(BaseModel):
    success: bool
    message: str


@router.get("/", response_model=ChannelStatusResponse)
async def get_channels_status() -> ChannelStatusResponse:
    """Get the status of all IM channels."""
    from app.channels.service import get_channel_service

    service = get_channel_service()
    if service is None:
        return ChannelStatusResponse(service_running=False, channels={})
    status = service.get_status()
    return ChannelStatusResponse(**status)


@router.post("/goconnect/webhook")
async def goconnect_webhook(request: Request) -> dict:
    """Receive inbound messages from GoConnect Chat Service."""
    from app.channels.service import get_channel_service

    service = get_channel_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Channel service not running")

    channel = service.get_channel("goconnect")
    if channel is None:
        raise HTTPException(status_code=503, detail="GoConnect channel not available")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    result = await channel.handle_webhook(payload, headers=dict(request.headers))
    if result.get("status") == "error":
        status_code = 401 if "token" in result.get("message", "") else 400
        raise HTTPException(status_code=status_code, detail=result.get("message", "Bad request"))
    return result


@router.get("/goconnect/webhook")
async def goconnect_webhook_health() -> dict:
    """Health check for GoConnect webhook endpoint."""
    return {"status": "ok", "channel": "goconnect", "type": "goconnect"}


# -- /hooks/goconnect alias (GoClaw convention) ----------------------------

hooks_router = APIRouter(prefix="/hooks", tags=["channels"])


@hooks_router.post("/goconnect")
async def goconnect_hooks_webhook(request: Request) -> dict:
    """Alias for /api/channels/goconnect/webhook (GoClaw convention)."""
    return await goconnect_webhook(request)


@hooks_router.get("/goconnect")
async def goconnect_hooks_health() -> dict:
    """Health check alias for /hooks/goconnect."""
    return await goconnect_webhook_health()


@router.post("/{name}/restart", response_model=ChannelRestartResponse)
async def restart_channel(name: str) -> ChannelRestartResponse:
    """Restart a specific IM channel."""
    from app.channels.service import get_channel_service

    service = get_channel_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Channel service is not running")

    success = await service.restart_channel(name)
    if success:
        logger.info("Channel %s restarted successfully", name)
        return ChannelRestartResponse(success=True, message=f"Channel {name} restarted successfully")
    else:
        logger.warning("Failed to restart channel %s", name)
        return ChannelRestartResponse(success=False, message=f"Failed to restart channel {name}")
