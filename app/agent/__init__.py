"""Three-mode CRM agent package (ASK · VISUALIZE · AGENT) built on LangGraph.

Public entry point is :func:`app.agent.router.run_mode`, which dispatches an
inbound chat turn to the correct mode graph.
"""

from app.agent.router import run_mode

__all__ = ["run_mode"]
