# Agent Routing Rules Contract

Allowed agents: chatgpt, claude_code, codex, hermes, operator

Allowed packet types: planning_prompt, implementation_prompt, review_prompt, audit_prompt, status_update_prompt, result_summary_prompt, manual_handoff_prompt

Allowed result statuses: success, pass, fail, blocked

Allowed review decisions: approved, rejected, needs_revision, blocked, manual_handoff_ready, none

Blocked routes: route plan status set to blocked and operator notified via manual_handoff_prompt.

Route conflict resolution: explicit operator decisions (rejected/needs_revision) override result-based rules. Exact matches preferred before broad matches.
