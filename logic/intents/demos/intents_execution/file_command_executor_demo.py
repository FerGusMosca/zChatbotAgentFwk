from __future__ import annotations
from typing import Optional
import json
from pathlib import Path
from langchain.prompts import ChatPromptTemplate


class FileCommandExecutor:
    """
    Execution service:
    - Reads the TXT file.
    - Sends the user's ACTION (free text) + the requested neighborhood (optional) + the file content to the LLM.
    - Returns a chat-friendly message based SOLELY on the LLM's structured JSON.
    - No heuristics/regex on our side; the LLM does ALL computations.
    """

    def __init__(self, logger, llm, exports_dir: str = "exports", max_chars: int = 24000):
        self.logger = logger
        self.llm = llm
        self.exports_dir = Path(exports_dir)
        self.max_chars = max_chars

        # Unified executor prompt: the LLM must interpret the ACTION and operate on the file.
        # NOTE: braces are escaped with double {{ }} to avoid format issues.
        self.exec_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a careful analyst of a plain-text export of real-estate listings.\n"
             "Each listing starts with a line beginning with '## ' followed by fields like "
             "'- Precio:', '- Ubicación:', '- Detalles:', '- Agencia:', '- URL:'.\n"
             "Your job is to EXECUTE the user's ACTION exactly as requested, using ONLY the provided file content.\n"
             "If the ACTION asks to 'show the whole file', provide a brief summary plus a SMALL representative sample; "
             "otherwise compute precisely what is requested (e.g., most expensive, best opportunities, by neighborhood, etc.).\n"
             "If a neighborhood is provided separately, treat it as a hard filter ONLY if the ACTION implies restriction.\n\n"
             "Return ONLY valid JSON with this schema:\n"
             "{{\n"
             "  \"result\": {{\n"
             "    \"summary\": <string>,\n"
             "    \"selections\": [\n"
             "      {{\n"
             "        \"header\": <string|null>,\n"
             "        \"price\": <string|null>,\n"
             "        \"location\": <string|null>,\n"
             "        \"details\": <string|null>,\n"
             "        \"url\": <string|null>\n"
             "      }}\n"
             "    ]\n"
             "  }}\n"
             "}}\n\n"
             "Rules:\n"
             "- Strict JSON. No markdown, no code fences.\n"
             "- If the ACTION mentions a number N (e.g., '3 propiedades', 'top 5'), RETURN EXACTLY N items in \"selections\" "
             "(or fewer ONLY if the file has less).\n"
             "- Each item in \"selections\" MUST come directly from the file content. Do not invent.\n"
             "- If a field is missing in the file, set it to null (not '(no header)').\n"
             "- Never collapse multiple results into one object; always use an array with N objects.\n"
             "- Keep the summary short, explaining the selection criterion.\n"
             "- If nothing matches, return an empty \"selections\" array and explain clearly in \"summary\"."),
            ("user",
             "ACTION (user words): {action}\n"
             "Neighborhood (optional): {neighborhood}\n"
             "File name: {filename}\n\n"
             "=== FILE CONTENT BEGIN ===\n{file_chunk}\n=== FILE CONTENT END ===\n\n"
             "Respond ONLY with strict JSON following the schema.")
        ])

    # Public API --------------------------------------------------------------

    def execute(self, filename: str, action: str, neighborhood: Optional[str] = None) -> str:
        """Execute the requested action purely via LLM (action is FREE TEXT)."""
        if self.logger: self.logger.error(f"[file_exec] action={action!r} neighborhood={neighborhood!r}")

        fpath = self._resolve_file(filename)
        if not fpath:
            return f"❌ File not found: {filename}"

        try:
            full = Path(fpath).read_text(encoding="utf-8")
        except Exception as ex:
            return f"❌ Could not read file {filename}: {ex!r}"

        file_chunk = full if len(full) <= self.max_chars else full[:self.max_chars]

        try:
            # --- LLM call ---
            msgs = self.exec_prompt.format_messages(
                action=(action or "").strip(),
                neighborhood=neighborhood or "",
                filename=Path(fpath).name,
                file_chunk=file_chunk
            )
            resp = self.llm.invoke(msgs)
            raw = getattr(resp, "content", None)

            if self.logger:
                preview = [{"role": m.type, "content": m.content} for m in msgs]
                self.logger.error(f"[exec_llm] msgs_preview={preview!r}")
                self.logger.error(f"[exec_llm] raw_type={type(raw).__name__} raw={raw!r}")

            # --- Parse & normalize ---
            summary, selections = self._parse_llm_result(resp)

            # --- Render output ---
            body = self._render_selections(summary, selections, neighborhood)
            return f"{body}\n📄 File: {Path(fpath).name}"

        except Exception as ex:
            if self.logger:
                self.logger.exception("exec_llm_error", extra={
                    "error": str(ex),
                    "filename": filename,
                    "action": action,
                    "neighborhood": neighborhood
                })
            return "❌ An error occurred while executing the command."

    # -------------------- Privates --------------------

    def _parse_llm_result(self, resp) -> tuple[str, list[dict]]:
        """
        Acepta respuesta como str o dict. Soporta:
          { "result": { "summary": "...", "selections": [ {...}, ... ] } }
        y retrocompat:
          { "result": { "summary": "...", "selection": { ... } } }
        Devuelve: (summary, [ {header, price, location, details, url}, ... ])
        """
        raw = getattr(resp, "content", None)

        # Convertir a dict robustamente
        if isinstance(raw, str):
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("` \n")
                idx = cleaned.find("{")
                if idx != -1:
                    cleaned = cleaned[idx:]
            try:
                data = json.loads(cleaned)
            except Exception as ex:
                if self.logger: self.logger.error(f"[exec_llm] json_error={ex!r}")
                data = getattr(resp, "additional_kwargs", {}) or {}
        elif isinstance(raw, dict):
            data = raw
        else:
            data = getattr(resp, "additional_kwargs", {}) or {}

        result = data.get("result", {}) if isinstance(data, dict) else {}
        summary = (result.get("summary") or "Done.").strip() if isinstance(result, dict) else "Done."

        selections = result.get("selections")
        if not isinstance(selections, list):
            # retrocompat con "selection" único
            sel = result.get("selection", {}) if isinstance(result, dict) else {}
            selections = [sel] if isinstance(sel, dict) and sel else []

        # Normalizar cada item a las 5 claves esperadas; forzar None si falta
        norm = []
        for sel in selections:
            if not isinstance(sel, dict):
                continue
            norm.append({
                "header": sel.get("header"),
                "price": sel.get("price"),
                "location": sel.get("location"),
                "details": sel.get("details"),
                "url": sel.get("url"),
            })
        return summary, norm

    def _render_selections(self, summary: str, selections: list[dict], neighborhood: Optional[str]) -> str:
        """
        Render numerado. No inventa placeholders: si el modelo puso null, mostramos '(null)'.
        """
        lines = [summary, ""]
        if not selections:
            lines.append("⚠️ No matching listings found.")
            return "\n".join(lines)

        scope = f" — neighborhood: {neighborhood}" if neighborhood else ""

        for i, sel in enumerate(selections, 1):
            header = sel.get("header") if sel.get("header") is not None else "(null)"
            price = sel.get("price") if sel.get("price") is not None else "(null)"
            location = sel.get("location") if sel.get("location") is not None else "(null)"
            details = sel.get("details") if sel.get("details") is not None else "(null)"
            url = sel.get("url") if sel.get("url") is not None else "(null)"

            lines += [
                f"#{i} ▸ 🏷️ {header}{scope}",
                f"     💵 {price}",
                f"     📍 {location}",
                f"     📐 {details}",
                f"     🔗 {url}",
                ""
            ]
        return "\n".join(lines)

    # Internals ---------------------------------------------------------------

    def _resolve_file(self, filename: str) -> Optional[str]:
        if self.logger: self.logger.error(f"[file_resolve] incoming={filename!r}")
        p = Path(filename)
        if p.exists() and p.is_file():
            if self.logger: self.logger.error(f"[file_resolve] absolute_hit={p}")
            return str(p)
        candidate = self.exports_dir / filename
        if self.logger: self.logger.error(f"[file_resolve] try_exports={candidate}")
        if candidate.exists() and candidate.is_file():
            if self.logger: self.logger.error(f"[file_resolve] exports_hit={candidate}")
            return str(candidate)
        if self.logger: self.logger.error(f"[file_resolve] MISS filename={filename!r} exports_dir={self.exports_dir}")
        return None
