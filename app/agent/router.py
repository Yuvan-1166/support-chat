"""Dispatch a chat turn to the correct mode graph (ASK · VISUALIZE · AGENT)."""

from __future__ import annotations

import asyncio
import logging

from app.agent.modes.agent import run_agent
from app.agent.modes.ask import run_ask
from app.agent.modes.visualize import run_visualize
from app.agent.state import AgentContext, ModeResult
from app.schemas.chat import ChatMode

logger = logging.getLogger(__name__)

_DISPATCH = {
    ChatMode.ASK: run_ask,
    ChatMode.VISUALIZE: run_visualize,
    ChatMode.AGENT: run_agent,
}


def run_mode_sync(mode: ChatMode, ctx: AgentContext, message: str) -> ModeResult:
    """Synchronous dispatch (graphs use the blocking Groq SDK + httpx)."""
    handler = _DISPATCH.get(mode)
    if handler is None:  # pragma: no cover - guarded by the enum
        return ModeResult(mode=str(mode), content="Unknown mode.", error="unknown_mode")
    return handler(ctx, message)


async def run_mode(mode: ChatMode, ctx: AgentContext, message: str) -> ModeResult:
    """Async entry point — runs the blocking graph in a thread pool so the
    FastAPI event loop stays free."""
    return await asyncio.to_thread(run_mode_sync, mode, ctx, message)
