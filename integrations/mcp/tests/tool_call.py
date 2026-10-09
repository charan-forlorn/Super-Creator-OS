"""tool_call.py — minimal helpers for driving an MCP tool server in-process.

Why not spin up a real stdio server?
------------------------------------
The real server would need a transport, a subprocess and an MCP client. The
behaviour under test — *does the tool touch the filesystem before validating the
path* — is fully observable at the ``FastMCP`` object level, so tests drive
``mcp.call_tool(...)`` directly and assert on its result/exception. That keeps
the suite hermetic (no subprocess, no port) while still exercising the real
``@mcp.tool`` wrappers, the real argument validation and the real guard call.

Result shape
------------
For a tool whose return type is not a structured-output model, ``call_tool``
returns ``(content_blocks, structured_output)`` where ``structured_output`` is a
dict containing the tool's raw return value. ``call_text`` extracts just that
value as a string.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError


def unwrap_tool_error(exc: ToolError) -> BaseException:
    """Re-raise the original exception FastMCP wrapped in a ToolError.

    ``ToolError.__cause__`` holds the exception the tool actually raised; tests
    need to assert on that (e.g. ``AllowRootViolation``), not on the wrapper.
    """
    return exc.__cause__ if exc.__cause__ is not None else exc


async def call_text(mcp: FastMCP, name: str, arguments: dict[str, Any]) -> str:
    """Invoke a tool and return its plain return value as a string."""
    _content, structured = await mcp.call_tool(name, arguments)
    result = structured.get("result") if isinstance(structured, dict) else None
    return result if isinstance(result, str) else ""


async def call_raw(mcp: FastMCP, name: str, arguments: dict[str, Any]) -> Any:
    """Invoke a tool and return its raw (possibly non-str) return value."""
    _content, structured = await mcp.call_tool(name, arguments)
    if isinstance(structured, dict):
        return structured.get("result")
    return structured
