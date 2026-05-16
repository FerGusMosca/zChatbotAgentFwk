# services/research_excel_importer.py
"""
Reads an uploaded Excel research grid, asks an LLM to extract a canonical
schema, and returns parsed rows ready for upsert_research_row().

Public API:
    list_sheets(file_bytes)                 -> list[str]
    extract_sheet(file_bytes, sheet_name)   -> list[dict]   # canonical rows
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

import openpyxl

from common.config.settings import settings
from common.llm.llm_factory import LLMFactory   # adjust import path if needed


# ── Prompt loading ─────────────────────────────────────────────────────
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "research_excel_extract.md"


def _load_prompt() -> str:
    """Reads the prompt template fresh every time so edits take effect
    without restarting the server (cheap: ~5KB file)."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


# ── Excel helpers ──────────────────────────────────────────────────────
def list_sheets(file_bytes: bytes) -> list[str]:
    """Returns the names of every sheet in the workbook."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _sheet_to_markdown(file_bytes: bytes, sheet_name: str) -> str:
    """Renders a sheet as a markdown table the LLM can read.

    Strategy:
    - Find the header row (first row with >= 3 non-empty cells).
    - Treat everything below as data rows.
    - Empty cells become ''.
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    try:
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"Sheet '{sheet_name}' not found")
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    # Find header row (first one with >=3 non-empty cells)
    header_idx = None
    for i, row in enumerate(rows):
        non_empty = sum(1 for c in row if c is not None and str(c).strip())
        if non_empty >= 3:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"Sheet '{sheet_name}' has no recognizable header row")

    headers = [(str(c).strip() if c is not None else f"col{j}")
               for j, c in enumerate(rows[header_idx])]
    # Drop trailing empty header columns
    while headers and not headers[-1]:
        headers.pop()
    n_cols = len(headers)

    md = ["| " + " | ".join(headers) + " |",
          "|" + "|".join(["---"] * n_cols) + "|"]

    for row in rows[header_idx + 1:]:
        cells = []
        for j in range(n_cols):
            v = row[j] if j < len(row) else None
            s = "" if v is None else str(v)
            # Markdown-safe cell content
            s = s.replace("|", "\\|").replace("\n", " ")
            cells.append(s.strip())
        # Skip totally empty rows
        if not any(cells):
            continue
        md.append("| " + " | ".join(cells) + " |")

    return "\n".join(md)


# ── LLM call + response parsing ────────────────────────────────────────
def _strip_json_fences(s: str) -> str:
    """Some LLM outputs wrap JSON in ```json ... ```; strip if present."""
    s = s.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, re.DOTALL)
    return m.group(1).strip() if m else s


def _coerce_decimal(v: Any) -> float | None:
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip()
    if not s or s.lower() in ("null", "none", "n/a", "na", "—", "s/d"):
        return None
    try:
        return float(s.replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def _coerce_str(v: Any) -> str:
    if v is None: return ""
    return str(v).strip()


CANONICAL_KEYS = (
    "symbol", "news", "gpa_ratio", "pe_ratio", "debt_ratio",
    "ta_situation", "mgmt_sentiment", "earnings", "conclusion",
    "latest_comments", "rating",
)


def _normalize_row(raw: dict) -> dict | None:
    """Coerce one raw LLM row into the canonical types our manager expects.
    Returns None for rows without a usable symbol."""
    sym = _coerce_str(raw.get("symbol")).upper()
    sym = re.sub(r"\s+", "", sym)
    if not sym or not re.match(r"^[A-Z][A-Z0-9.\-]{0,15}$", sym):
        return None
    return {
        "symbol":          sym,
        "news":            _coerce_str(raw.get("news")),
        "gpa_ratio":       _coerce_decimal(raw.get("gpa_ratio")),
        "pe_ratio":        _coerce_decimal(raw.get("pe_ratio")),
        "debt_ratio":      _coerce_decimal(raw.get("debt_ratio")),
        "ta_situation":    _coerce_str(raw.get("ta_situation")),
        "mgmt_sentiment":  _coerce_str(raw.get("mgmt_sentiment")),
        "earnings":        _coerce_str(raw.get("earnings")),
        "conclusion":      _coerce_str(raw.get("conclusion")),
        "latest_comments": _coerce_str(raw.get("latest_comments")),
        "rating":          _coerce_decimal(raw.get("rating")),
    }


def extract_sheet(file_bytes: bytes, sheet_name: str) -> list[dict]:
    """Renders the sheet to markdown, asks the LLM to map it to the canonical
    schema, parses the response, and returns a list of normalized row dicts.

    Each dict has the keys in CANONICAL_KEYS and types ready for upsert.
    """
    table_md = _sheet_to_markdown(file_bytes, sheet_name)
    prompt = (
        _load_prompt()
        + "\n\n## SHEET DATA — sheet name: "
        + sheet_name
        + "\n\n"
        + table_md
    )

    llm = LLMFactory.create(
        provider="openai",
        model_name=settings.openai_model or "gpt-4o",
        temperature=0.0,
    )
    raw_response = llm.invoke(prompt)
    raw_response = _strip_json_fences(raw_response)

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        snippet = raw_response[:400]
        raise ValueError(f"LLM returned invalid JSON: {e}. First 400 chars:\n{snippet}")

    rows_raw = data.get("rows") if isinstance(data, dict) else data
    if not isinstance(rows_raw, list):
        raise ValueError("LLM JSON missing 'rows' array")

    out = []
    for r in rows_raw:
        if not isinstance(r, dict):
            continue
        norm = _normalize_row(r)
        if norm is not None:
            out.append(norm)
    return out