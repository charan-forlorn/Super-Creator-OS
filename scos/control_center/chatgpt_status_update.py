"""SCOS Stage 5.7 ChatGPT status update helper renderers.

Thin wrappers around ``result_intake_builder.build_chatgpt_status_update_packet``
plus a deterministic Markdown renderer for the resulting packet. This module
NEVER sends anything to ChatGPT, never opens a network connection, never
touches a clipboard, and never automates a browser/app — every function here
only ever produces local data/text for a human to paste manually.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

try:
    from .result_intake_builder import build_chatgpt_status_update_packet
    from .result_intake_models import AIResultIntakeError, ChatGPTStatusUpdatePacket
except ImportError:  # direct-module execution (tests insert the package dir)
    from result_intake_builder import build_chatgpt_status_update_packet
    from result_intake_models import AIResultIntakeError, ChatGPTStatusUpdatePacket

CHATGPT_STATUS_UPDATE_SCHEMA_VERSION = 1


def prepare_chatgpt_status_update(
    *,
    intake_record,
    target_runtime_id: str,
    created_at: str,
    requested_chatgpt_action: str,
    metadata=None,
) -> ChatGPTStatusUpdatePacket | AIResultIntakeError:
    """Build a ``ChatGPTStatusUpdatePacket`` for ``intake_record``.

    This is a manual-handoff artifact only: it is never dispatched to
    ChatGPT, a clipboard, or a network by this function.
    """
    return build_chatgpt_status_update_packet(
        intake_record=intake_record,
        target_runtime_id=target_runtime_id,
        created_at=created_at,
        requested_chatgpt_action=requested_chatgpt_action,
        metadata=metadata,
    )


def render_chatgpt_status_update_markdown(packet: ChatGPTStatusUpdatePacket) -> str:
    """Render ``packet`` as deterministic Markdown for manual pasting.

    Always includes session/task IDs, source agent (read from packet
    metadata), verdict, normalized summary, evidence references, the
    requested ChatGPT action, and the fixed manual-handoff constraints.
    """
    if not isinstance(packet, ChatGPTStatusUpdatePacket):
        raise ValueError(
            "NOT_A_CHATGPT_STATUS_UPDATE_PACKET: packet must be a "
            "ChatGPTStatusUpdatePacket instance"
        )

    source_agent = packet.metadata.get("source_agent", "unknown")
    evidence_lines = (
        "\n".join(f"- {ref}" for ref in packet.evidence_refs)
        if packet.evidence_refs
        else "- None"
    )

    return (
        f"# ChatGPT Status Update — {packet.title}\n"
        "\n"
        f"- **Session:** {packet.session_id}\n"
        f"- **Task:** {packet.task_id}\n"
        f"- **Source Agent:** {source_agent}\n"
        f"- **Verdict:** {packet.result_verdict}\n"
        f"- **Requested ChatGPT Action:** {packet.requested_chatgpt_action}\n"
        "\n"
        "## Summary\n"
        "\n"
        f"{packet.result_summary}\n"
        "\n"
        "## Status Update Body\n"
        "\n"
        f"{packet.status_update_body}\n"
        "\n"
        "## Evidence\n"
        "\n"
        f"{evidence_lines}\n"
        "\n"
        "## Constraints\n"
        "\n"
        "- Do not assume hidden files.\n"
        "- Do not claim work committed/pushed unless evidence says so.\n"
        "- Produce next action only from provided evidence.\n"
        "\n"
        "_This is a manual handoff artifact. Copy this text into ChatGPT "
        "yourself — nothing here is sent automatically._"
    )
