"""Read and write the module-level assignments in settings.py in place.

The goal is to let the app edit settings and persist them back to settings.py
without destroying comments, blank lines, or ordering. We only rewrite the
value portion of each top-level ``name = value`` line.
"""

import ast
import re
from pathlib import Path

SETTINGS_FILE = Path(__file__).with_name("settings.py")

# Matches a top-level assignment like:  name = <value>   # optional comment
# Group 1 = leading name and equals (kept verbatim), group "val" = value text.
_ASSIGN_RE = re.compile(r"^(?P<lead>([A-Za-z_]\w*)\s*=\s*)(?P<val>.*?)\s*$")


def _split_value_and_comment(value_text):
    """Split a value line into (code, comment). Respects quotes so a '#'
    inside a string is not treated as a comment. Returns comment including
    its leading whitespace and '#', or '' if none."""
    in_str = None
    for i, ch in enumerate(value_text):
        if in_str:
            if ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
        elif ch == "#":
            return value_text[:i].rstrip(), value_text[i:]
    return value_text.rstrip(), ""


def load():
    """Return an ordered dict of {name: python_value} for every top-level
    assignment in settings.py."""
    result = {}
    for line in SETTINGS_FILE.read_text(encoding="utf-8").splitlines():
        m = _ASSIGN_RE.match(line)
        if not m:
            continue
        name = m.group(2)
        code, _comment = _split_value_and_comment(m.group("val"))
        try:
            result[name] = ast.literal_eval(code)
        except (ValueError, SyntaxError):
            # Skip anything that isn't a simple literal (imports, exprs, etc.)
            continue
    return result


def save(values):
    """Write ``values`` (a dict of {name: python_value}) back into
    settings.py, rewriting only the value of matching assignment lines and
    preserving comments, blank lines, and ordering."""
    lines = SETTINGS_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    for line in lines:
        stripped = line.rstrip("\r\n")
        newline = line[len(stripped):]  # preserve original EOL
        m = _ASSIGN_RE.match(stripped)
        if m and m.group(2) in values:
            _code, comment = _split_value_and_comment(m.group("val"))
            new_val = repr(values[m.group(2)])
            rebuilt = m.group("lead") + new_val
            if comment:
                rebuilt += "  " + comment
            out.append(rebuilt + newline)
        else:
            out.append(line)
    SETTINGS_FILE.write_text("".join(out), encoding="utf-8")
