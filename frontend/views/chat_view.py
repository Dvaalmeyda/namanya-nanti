"""Tampilan antarmuka utama tanya-jawab dokumen berbasis RAG (Chat View)."""

import streamlit as st
from frontend.client.chat_client import ChatClient
from frontend.components.chat_bubble import render_chat_message
from frontend.state.chat_state import (
    add_assistant_message,
    add_user_message,
    get_history_for_api,
    get_messages,
)


def render_chat_view() -> None:
    """Merender riwayat obrolan dan formulir pengiriman pertanyaan RAG."""
    messages = get_messages()

    # Render pesan-pesan sebelumnya
    for idx, msg in enumerate(messages):
        render_chat_message(msg, index=idx)

    # Input pesan pengguna
    user_prompt = st.chat_input("Tanyakan sesuatu berdasarkan dokumen Anda...")
    if not user_prompt:
        return

    # Tambahkan pesan pengguna ke state dan render segera
    add_user_message(user_prompt)
    with st.chat_message("user"):
        st.markdown(user_prompt)

    # Parameter sesi saat ini
    history = get_history_for_api(max_turns=3)
    streaming = st.session_state.get("streaming_mode", True)
    folders = st.session_state.get("selected_folders") or None
    file_types = st.session_state.get("selected_file_types") or None
    top_k = st.session_state.get("top_k", 4)

    client = ChatClient()

    with st.chat_message("assistant"):
        if streaming:
            _handle_streaming_chat(client, user_prompt, history, folders, file_types, top_k)
        else:
            _handle_sync_chat(client, user_prompt, history, folders, file_types, top_k)

    st.rerun()


def _handle_streaming_chat(client, question, history, folders, file_types, top_k) -> None:
    """Menjalankan obrolan dalam mode streaming token-demi-token SSE."""
    placeholder = st.empty()
    full_content = ""
    sources = []
    timing = {}
    refused = False
    refusal_reason = None

    try:
        for event in client.chat_stream(question, history, folders, file_types, top_k):
            ev_type = event.event
            data = event.data

            if ev_type == "token":
                token = data.get("content", "")
                full_content += token
                placeholder.markdown(full_content + "...")
            elif ev_type == "sources":
                sources = data.get("sources", [])
            elif ev_type == "done":
                refused = data.get("refused", False)
                refusal_reason = data.get("refusal_reason")
                timing = data.get("timing", {})

        placeholder.markdown(full_content)

        trace = {
            "question": question,
            "history": history,
            "sources": sources,
            "timing": timing,
            "refused": refused,
            "refusal_reason": refusal_reason,
        }
        add_assistant_message(full_content, sources, refused, refusal_reason, timing, trace)

    except Exception as exc:
        placeholder.error(f"Gagal memproses streaming: {exc}")


def _handle_sync_chat(client, question, history, folders, file_types, top_k) -> None:
    """Menjalankan obrolan dalam mode non-streaming JSON utuh."""
    with st.spinner("Mencari dokumen dan menghasilkan jawaban..."):
        try:
            res = client.chat_sync(question, history, folders, file_types, top_k, include_chunks=True)
            content = res.get("answer", "")
            sources = res.get("sources", [])
            refused = res.get("refused", False)
            refusal_reason = res.get("refusal_reason")
            timing = res.get("timing", {})

            st.markdown(content)

            trace = {
                "question": question,
                "history": history,
                "sources": sources,
                "timing": timing,
                "refused": refused,
                "refusal_reason": refusal_reason,
            }
            add_assistant_message(content, sources, refused, refusal_reason, timing, trace)
        except Exception as exc:
            st.error(f"Gagal memproses permintaan chat: {exc}")
