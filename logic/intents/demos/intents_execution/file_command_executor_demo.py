from __future__ import annotations
from typing import Optional
import json
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

from common.util.loader.intent_prompt_loader import IntentPromptLoader
from common.util.loader.prompt_loader import PromptLoader


class FileCommandExecutor:
    """
    Execution service:
    - Reads the TXT file.
    - Sends the user's ACTION (free text) + the requested neighborhood (optional) + the file content to the LLM.
    - Returns a chat-friendly message based SOLELY on the LLM's structured JSON.
    - No heuristics/regex on our side; the LLM does ALL computations.
    """

    def __init__(self, logger, llm, exports_dir: str = "exports", max_chars: int = 80000):
        self.logger = logger
        self.llm = llm
        self.exports_dir = Path(exports_dir)
        self.max_chars = max_chars

        # Unified executor prompt: the LLM must interpret the ACTION and operate on the file.
        # NOTE: braces are escaped with double {{ }} to avoid format issues.
        sys_txt = IntentPromptLoader.get_text("command_executor_exec_prompt_system")
        usr_txt = IntentPromptLoader.get_text("command_executor_exec_prompt_user")

        self.exec_prompt = ChatPromptTemplate.from_messages([
            ("system", sys_txt),
            ("user", usr_txt),
        ])

    # Public API --------------------------------------------------------------

    def _smart_chunk(self, text: str) -> str:
        if len(text) <= self.max_chars:
            return text
        cut = text[: self.max_chars]
        # buscar el último inicio de listing
        anchor = cut.rfind("\n## ")
        if anchor == -1:
            return cut  # fallback
        return cut[:anchor].rstrip()

    def _est_tokens(self, s: str) -> int:
        # Regla rápida ~4 chars/token (sirve para monitorear)
        try:
            return max(1, int(len(s) / 4))
        except Exception:
            return -1

    def execute(self, filename: str, action: str, neighborhood: Optional[str] = None) -> str:
        """Execute the requested action purely via LLM (action is FREE TEXT)."""
        if self.logger:
            self.logger.error(
                "[file_exec:init] action=%r neighborhood=%r exports_dir=%s max_chars=%s",
                action, neighborhood, str(self.exports_dir), self.max_chars
            )

        fpath = self._resolve_file(filename)
        if not fpath:
            return f"❌ File not found: {filename}"

        # ---- Lectura del archivo
        try:
            full = Path(fpath).read_text(encoding="utf-8")
        except Exception as ex:
            return f"❌ Could not read file {filename}: {ex!r}"

        truncated = len(full) > self.max_chars
        file_chunk = self._smart_chunk(full)
        truncated = len(full) > len(file_chunk)
        if self.logger:
            self.logger.error("[file_exec:truncate] truncated=%s sent_chars=%d", truncated, len(file_chunk))

        # Métricas previas
        if self.logger:
            self.logger.error(
                "[file_exec:metrics] file_chars_total=%d  file_chars_sent=%d  truncated=%s  "
                "sys_chars=%d usr_chars=%d  action_chars=%d  neigh_chars=%d",
                len(full), len(file_chunk), truncated,
                # ojo: estos vienen de los prompts ya cargados
                len(IntentPromptLoader.get_text('command_executor_exec_prompt_system')),
                len(IntentPromptLoader.get_text('command_executor_exec_prompt_user')),
                len(action or ""), len((neighborhood or ""))
            )
            self.logger.error(
                "[file_exec:tokens_est] file_tokens~%d  sys_tokens~%d  usr_tokens~%d",
                self._est_tokens(file_chunk),
                self._est_tokens(IntentPromptLoader.get_text('command_executor_exec_prompt_system')),
                self._est_tokens(IntentPromptLoader.get_text('command_executor_exec_prompt_user')),
            )

        try:
            # ---- LLM call
            msgs = self.exec_prompt.format_messages(
                action=(action or "").strip(),
                neighborhood=neighborhood or "",
                filename=Path(fpath).name,
                file_chunk=file_chunk
            )
            # log de preview (solo tamaños para no inundar)
            if self.logger:
                preview_sizes = [{"role": m.type, "chars": len(m.content or "")} for m in msgs]
                self.logger.error("[exec_llm:preview_sizes] %r", preview_sizes)

            resp = self.llm.invoke(msgs)
            raw = getattr(resp, "content", None)

            # logs crudos
            if self.logger:
                self.logger.error("[exec_llm:raw_type] %s", type(raw).__name__)
                self.logger.error("[exec_llm:raw_snippet] %s",
                                  (raw[:600] + "…") if isinstance(raw, str) and len(raw) > 600 else raw)

                # si el cliente expone usage/tokens
                meta = getattr(resp, "response_metadata", {}) or {}
                self.logger.error("[exec_llm:response_metadata] %r", meta)

            # ---- Parse & normalize
            summary, selections = self._parse_llm_result(resp)

            # ---- Render
            body = self._render_selections(summary, selections, neighborhood)
            out = f"{body}\n📄 File: {Path(fpath).name}"

            # Post-metrics útiles
            if self.logger:
                self.logger.error(
                    "[file_exec:done] selections=%d  summary_chars=%d  out_chars=%d",
                    len(selections), len(summary or ""), len(out)
                )
            return out

        except Exception as ex:
            if self.logger:
                self.logger.exception("exec_llm_error", extra={
                    "error": str(ex),
                    "src_filename": filename,
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
