import builtins
import contextlib
import io
import sys
from pathlib import Path
from typing import Any

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

_serde = JsonPlusSerializer()


def _is_checkpoint_safe(value: Any) -> bool:
    """Return True if LangGraph's checkpoint serializer can handle this value."""
    try:
        _serde.dumps_typed(value)
    except Exception:
        return False
    return True


def local_python_sandbox(code: str, local_context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Execute trusted local Python code and return stdout plus newly created vars.

    This is intentionally not a security sandbox. It is for local CLI demo use only.

    Uses a fresh globals dict per call to avoid polluting the global builtins
    module across executions, and to avoid the classic exec(code, globals, locals)
    two-dict bug where top-level function defs cannot see sibling assignments.
    """
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    exec_namespace: dict[str, Any] = {"__builtins__": builtins, **local_context}
    original_keys = set(exec_namespace.keys())

    try:
        with contextlib.redirect_stdout(io.StringIO()) as output_buffer:
            exec(code, exec_namespace)
        output = output_buffer.getvalue() or "<code ran, no output printed to stdout>"
    except Exception as exc:
        output = f"Error during execution: {repr(exc)}"

    # Probe each new value with LangGraph's own checkpoint serializer and drop the
    # ones it can't handle (modules, file handles, sockets, locks, generators,
    # user-defined functions/classes, etc.). Plain data round-trips fine.
    new_keys = set(exec_namespace.keys()) - original_keys
    new_vars = {
        key: exec_namespace[key]
        for key in new_keys
        if _is_checkpoint_safe(exec_namespace[key])
    }
    return output, new_vars
