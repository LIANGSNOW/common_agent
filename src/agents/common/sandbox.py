import builtins
import contextlib
import io
import sys
from pathlib import Path
from typing import Any


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

    new_keys = set(exec_namespace.keys()) - original_keys
    new_vars = {key: exec_namespace[key] for key in new_keys}
    return output, new_vars
