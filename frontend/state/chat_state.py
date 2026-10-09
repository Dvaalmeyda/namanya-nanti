"""Pengelolaan riwayat percakapan dan alur kerja trace per giliran."""

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
import streamlit as st


@dataclass
class ChatMessage:
    """Struktur data satu giliran pesan percakapan."""

    role: str
    content: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    refused: bool = False
    refusal_reason: Optional[str] = None
    timing: dict[str, Any] = field(default_factory=dict)
    workflow_trace: dict[str, Any] = field(default_factory=dict)


def get_messages() -> list[dict[str, Any]]:
    """Mengambil daftar riwayat pesan percakapan dari state."""
    return st.session_state.get("messages", [])


def add_user_message(question: str) -> None:
    """Menambahkan pesan pertanyaan pengguna ke riwayat percakapan."""
    msg = ChatMessage(role="user", content=question)
    st.session_state.setdefault("messages", []).append(asdict(msg))


def add_assistant_message(
    content: str,
    sources: Optional[list[dict[str, Any]]] = None,
    refused: bool = False,
    refusal_reason: Optional[str] = None,
    timing: Optional[dict[str, Any]] = None,
    workflow_trace: Optional[dict[str, Any]] = None,
) -> None:
    """Menambahkan respons asisten beserta sitasi dan trace alur kerja."""
    msg = ChatMessage(
        role="assistant",
        content=content,
        sources=sources or [],
        refused=refused,
        refusal_reason=refusal_reason,
        timing=timing or {},
        workflow_trace=workflow_trace or {},
    )
    st.session_state.setdefault("messages", []).append(asdict(msg))


def clear_chat_history() -> None:
    """Mengosongkan riwayat percakapan di session state."""
    st.session_state["messages"] = []


def get_history_for_api(max_turns: int = 3) -> list[dict[str, str]]:
    """Membentuk riwayat percakapan untuk payload API (maksimal max_turns terakhir)."""
    messages = get_messages()
    history: list[dict[str, str]] = []
    # Ambil pesan sebelum kueri terakhir
    for m in messages[:-1]:
        if m.get("role") in ("user", "assistant"):
            history.append({
                "role": m["role"],
                "content": m.get("content", ""),
            })
    return history[-max_turns * 2:] if len(history) > max_turns * 2 else history
