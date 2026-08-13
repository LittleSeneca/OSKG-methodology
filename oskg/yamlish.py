"""A YAML subset, parsed and emitted without dependencies.

`oskg` runs on a bare system `python3` with no venv — that is a deliberate
constraint, because the machine that runs an unattended overnight build should
not also need a maintained virtualenv. PyYAML is the only dependency the
pipeline would otherwise need, and the YAML it would parse is a small, closed
subset: manifests and markdown frontmatter.

Supported
---------
* ``key: scalar`` at any indent depth
* ``key:`` followed by an indented block list of scalars (``- item``)
* nested mappings to arbitrary depth, by indentation
* inline lists of scalars: ``[a, b, c]`` / ``[]``
* inline mappings of scalars: ``{a: 1}`` / ``{}``
* ``#`` comments, single/double-quoted strings, ``---`` document markers

Deliberately rejected, loudly rather than misparsed
---------------------------------------------------
Anchors and aliases, block scalars (``|``, ``>``), lists of mappings, multiple
documents, and complex keys. A manifest that needs those is doing something the
schema does not intend, and silently dropping the parts we cannot read would be
the worst outcome — see `YamlishError`.

Dates are returned as strings. YAML would give you a ``datetime.date``; every
consumer here wants the ISO text it was written with, and round-tripping a date
object through the emitter is a needless way to change a file nobody edited.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["YamlishError", "loads", "dumps", "load_file", "dump_file"]


class YamlishError(ValueError):
    """Raised on YAML this parser will not attempt to understand."""

    def __init__(self, message: str, line_no: int | None = None, line: str = ""):
        self.line_no = line_no
        self.line = line
        if line_no is not None:
            message = f"line {line_no}: {message}"
            if line.strip():
                message += f"\n  {line.rstrip()}"
        super().__init__(message)


_KEY_RE = re.compile(r"^(?P<key>[A-Za-z_][\w./-]*|\"[^\"]+\"|'[^']+')\s*:(?:\s+(?P<val>.*))?$")
_LIST_ITEM_RE = re.compile(r"^-\s*(?P<val>.*)$")
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")

_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}
_NULL = {"", "null", "~"}


# ─────────────────────────────────────────────────────────────────────────────
# Scanning
# ─────────────────────────────────────────────────────────────────────────────


class _Line:
    __slots__ = ("no", "indent", "text", "raw")

    def __init__(self, no: int, raw: str):
        self.no = no
        self.raw = raw
        stripped = _strip_comment(raw)
        self.text = stripped.strip()
        self.indent = len(stripped) - len(stripped.lstrip(" "))


def _strip_comment(line: str) -> str:
    """Remove a trailing ``#`` comment, respecting quotes.

    ``url: "http://x#y"`` must survive; ``key: value  # note`` must not keep the
    note. A ``#`` only opens a comment at the start of a line or after
    whitespace, which is the rule real YAML uses too.
    """
    out: list[str] = []
    quote: str | None = None
    prev_ws = True
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            prev_ws = False
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            prev_ws = False
            continue
        if ch == "#" and prev_ws:
            break
        out.append(ch)
        prev_ws = ch in " \t"
    return "".join(out).rstrip()


def _scan(text: str) -> list[_Line]:
    lines: list[_Line] = []
    seen_content = False
    for i, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlishError("tab in indentation; use spaces", i, raw)
        stripped = raw.strip()
        if stripped in ("---", "..."):
            if seen_content and stripped == "---":
                raise YamlishError("multiple documents are not supported", i, raw)
            continue
        ln = _Line(i, raw)
        if not ln.text:
            continue
        _reject_unsupported(ln)
        seen_content = True
        lines.append(ln)
    return lines


def _reject_unsupported(ln: _Line) -> None:
    t = ln.text
    if t.startswith("<<:"):
        raise YamlishError("merge keys are not supported", ln.no, ln.raw)
    if re.search(r":\s*[|>][+-]?\s*$", t):
        raise YamlishError("block scalars (| and >) are not supported", ln.no, ln.raw)

    m = _LIST_ITEM_RE.match(t)
    if m and _KEY_RE.match(m.group("val").strip()):
        raise YamlishError("lists of mappings are not supported", ln.no, ln.raw)

    # Anchors and aliases can sit at the start of a line (`- &a x`) or in the
    # value position (`key: &a x`). Both would silently lose their binding here,
    # so look at whichever part actually holds the value.
    value = t
    if m:
        value = m.group("val").strip()
    else:
        km = _KEY_RE.match(t)
        if km:
            value = (km.group("val") or "").strip()
    if value[:1] in ("&", "*"):
        raise YamlishError("anchors and aliases are not supported", ln.no, ln.raw)


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────


def loads(text: str) -> dict[str, Any]:
    """Parse a YAML-subset document into a dict. Empty input yields ``{}``."""
    lines = _scan(text)
    if not lines:
        return {}
    value, consumed = _parse_block(lines, 0, lines[0].indent)
    if consumed != len(lines):
        ln = lines[consumed]
        raise YamlishError("unexpected indentation", ln.no, ln.raw)
    if not isinstance(value, dict):
        raise YamlishError("document root must be a mapping", lines[0].no, lines[0].raw)
    return value


def _parse_block(lines: list[_Line], start: int, indent: int) -> tuple[Any, int]:
    """Parse the run of lines at exactly `indent`. Returns (value, next_index)."""
    if start >= len(lines):
        return {}, start
    if _LIST_ITEM_RE.match(lines[start].text):
        return _parse_list(lines, start, indent)
    return _parse_mapping(lines, start, indent)


def _parse_mapping(lines: list[_Line], start: int, indent: int) -> tuple[dict, int]:
    out: dict[str, Any] = {}
    i = start
    while i < len(lines):
        ln = lines[i]
        if ln.indent < indent:
            break
        if ln.indent > indent:
            raise YamlishError("unexpected indentation", ln.no, ln.raw)

        m = _KEY_RE.match(ln.text)
        if not m:
            raise YamlishError(f"expected 'key: value', got {ln.text!r}", ln.no, ln.raw)

        key = _unquote(m.group("key"))
        rest = (m.group("val") or "").strip()
        i += 1

        if rest:
            out[key] = _parse_scalar_or_inline(rest, ln)
            continue

        # Value is on following lines, indented deeper — or absent (→ None).
        if i < len(lines) and lines[i].indent > indent:
            out[key], i = _parse_block(lines, i, lines[i].indent)
        else:
            out[key] = None
    return out, i


def _parse_list(lines: list[_Line], start: int, indent: int) -> tuple[list, int]:
    out: list[Any] = []
    i = start
    while i < len(lines):
        ln = lines[i]
        if ln.indent < indent:
            break
        if ln.indent > indent:
            raise YamlishError("unexpected indentation in list", ln.no, ln.raw)
        m = _LIST_ITEM_RE.match(ln.text)
        if not m:
            break
        out.append(_parse_scalar_or_inline(m.group("val").strip(), ln))
        i += 1
    return out, i


def _parse_scalar_or_inline(raw: str, ln: _Line) -> Any:
    if raw.startswith("["):
        return _parse_inline_list(raw, ln)
    if raw.startswith("{"):
        return _parse_inline_mapping(raw, ln)
    return _parse_scalar(raw)


def _split_inline(body: str, ln: _Line, closer: str) -> list[str]:
    """Split a flow collection body on commas that are not inside quotes."""
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch in "[]{}":
            raise YamlishError(f"nested inline collections are not supported", ln.no, ln.raw)
        if ch == ",":
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if quote:
        raise YamlishError("unterminated quote", ln.no, ln.raw)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_inline_list(raw: str, ln: _Line) -> list:
    if not raw.endswith("]"):
        raise YamlishError("unterminated inline list", ln.no, ln.raw)
    return [_parse_scalar(p) for p in _split_inline(raw[1:-1], ln, "]")]


def _parse_inline_mapping(raw: str, ln: _Line) -> dict:
    if not raw.endswith("}"):
        raise YamlishError("unterminated inline mapping", ln.no, ln.raw)
    out: dict[str, Any] = {}
    for part in _split_inline(raw[1:-1], ln, "}"):
        if ":" not in part:
            raise YamlishError(f"expected 'key: value' in inline mapping, got {part!r}", ln.no, ln.raw)
        k, _, v = part.partition(":")
        out[_unquote(k.strip())] = _parse_scalar(v.strip())
    return out


def _unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        inner = s[1:-1]
        if s[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")
        return inner.replace("''", "'")
    return s


def _parse_scalar(raw: str) -> Any:
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return _unquote(s)
    low = s.lower()
    if low in _NULL:
        return None
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s) and not _INT_RE.match(s):
        try:
            return float(s)
        except ValueError:
            pass
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Emitting
# ─────────────────────────────────────────────────────────────────────────────

# Bare strings that YAML — or this parser — would read back as something other
# than a string. Quoting these on the way out is what makes a round trip safe.
_AMBIGUOUS = _TRUE | _FALSE | {"null", "~", ""}
_NEEDS_QUOTE_RE = re.compile(r"^[\s\[\]{}>|*&!%@`#-]|[:#]\s|\s$|[\n\"']")


def dumps(data: dict[str, Any], *, indent: int = 0) -> str:
    """Emit a dict as YAML in the supported subset.

    Round-trips through `loads` for any value this module can represent:
    dicts, lists of scalars, str, int, float, bool, None.
    """
    if not isinstance(data, dict):
        raise YamlishError("top level must be a mapping")
    return "".join(_emit_mapping(data, indent))


def _emit_mapping(data: dict[str, Any], indent: int) -> list[str]:
    pad = " " * indent
    out: list[str] = []
    for key, value in data.items():
        k = _emit_key(str(key))
        if isinstance(value, dict):
            if not value:
                out.append(f"{pad}{k}: {{}}\n")
            else:
                out.append(f"{pad}{k}:\n")
                out.extend(_emit_mapping(value, indent + 2))
        elif isinstance(value, (list, tuple)):
            if not value:
                out.append(f"{pad}{k}: []\n")
            else:
                out.append(f"{pad}{k}:\n")
                for item in value:
                    if isinstance(item, (dict, list, tuple)):
                        raise YamlishError("cannot emit a list of collections")
                    out.append(f"{pad}  - {_emit_scalar(item)}\n")
        else:
            out.append(f"{pad}{k}: {_emit_scalar(value)}\n")
    return out


def _emit_key(key: str) -> str:
    return f'"{key}"' if _NEEDS_QUOTE_RE.search(key) or key.lower() in _AMBIGUOUS else key


def _emit_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    s = str(value)
    if s.lower() in _AMBIGUOUS or _NEEDS_QUOTE_RE.search(s) or _INT_RE.match(s) or _FLOAT_RE.match(s):
        escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return s


# ─────────────────────────────────────────────────────────────────────────────
# File helpers
# ─────────────────────────────────────────────────────────────────────────────


def load_file(path) -> dict[str, Any]:
    from pathlib import Path

    p = Path(path)
    try:
        return loads(p.read_text(encoding="utf-8"))
    except YamlishError as exc:
        raise YamlishError(f"{p}: {exc}") from exc


def dump_file(path, data: dict[str, Any], *, header: str = "") -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(header + dumps(data), encoding="utf-8")
