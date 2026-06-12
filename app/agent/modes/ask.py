"""ASK mode — RAG-grounded help & navigation (no DB, no actions).

A minimal LangGraph: ``retrieve`` (Chroma top-k) → ``answer`` (LLM grounded on
the retrieved chunks).  Guardrails: knowledge-only, refuse data/action requests,
never invent navigation, "I don't know" fallback.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.agent.guardrails import ASK_REFUSAL, ask_out_of_scope
from app.agent.state import AgentContext, ModeResult
from app.core.llm import get_llm_client
from app.rag.store import get_knowledge_store

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are the in-app help assistant for a CRM platform. Answer the user's "
    "question about how the CRM works and where to find features, using ONLY "
    "the knowledge snippets provided below. Rules:\n"
    "- Ground every claim in the snippets. Do NOT invent menu names, URLs, or steps.\n"
    "- If the snippets don't contain the answer, say you don't have that "
    "information and suggest the closest relevant area.\n"
    "- Be concise and practical: give step-by-step navigation when relevant.\n"
    "- You cannot run queries or take actions here; if asked to, tell the user "
    "to switch to VISUALIZE (data insights) or AGENT (actions) mode.\n"
)


class AskState(TypedDict, total=False):
    message: str
    snippets: list[dict]
    answer: str


def _node_retrieve(state: AskState) -> AskState:
    store = get_knowledge_store()
    state["snippets"] = store.retrieve(state["message"])
    return state


def _node_answer(state: AskState) -> AskState:
    snippets = state.get("snippets") or []
    if not snippets:
        state["answer"] = (
            "I don't have documentation indexed for that yet. Try rephrasing, "
            "or ask an administrator to add the relevant help docs."
        )
        return state

    context = "\n\n---\n\n".join(
        f"[source: {s['metadata'].get('source', '?')}]\n{s['text']}" for s in snippets
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"KNOWLEDGE SNIPPETS:\n{context}\n\nQUESTION: {state['message']}"},
    ]
    state["answer"] = get_llm_client().chat_completion(messages, temperature=0.2)
    return state


def _build_graph():
    g = StateGraph(AskState)
    g.add_node("retrieve", _node_retrieve)
    g.add_node("answer", _node_answer)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "answer")
    g.add_edge("answer", END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


def run_ask(ctx: AgentContext, message: str) -> ModeResult:
    """Answer a how-to / navigation question from indexed knowledge."""
    if ask_out_of_scope(message):
        return ModeResult(mode="ask", content=ASK_REFUSAL)

    try:
        final = _graph().invoke({"message": message})
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("ASK mode failed")
        return ModeResult(mode="ask", content="Sorry, I hit an error answering that.", error=str(exc))

    snippets = final.get("snippets") or []
    return ModeResult(
        mode="ask",
        content=final.get("answer", ""),
        sources=[{"source": s["metadata"].get("source"), "distance": s.get("distance")} for s in snippets],
    )
