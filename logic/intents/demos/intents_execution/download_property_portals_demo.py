# logic/intents/demos/download_property_portals_demo.py
from __future__ import annotations
from datetime import datetime
from typing import Dict, Optional
from anyio import Path
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import os
from logic.intents.base_intent_logic_demo import BaseIntentLogicDemo
from logic.intents.demos.intents_execution.real_state_parsers.download_argenprop_property_demo import \
    DownloadArgenpropPropertyDemo
from logic.intents.demos.intents_execution.real_state_parsers.download_zonaprop_property_demo import (
    DownloadZonapropPropertyDemo
)
from logic.intents.demos.intents_execution.real_state_parsers.models import ZpListing
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


class DownloadPropertyPortalsIntentLogicDemo(BaseIntentLogicDemo):
    """
    Intent: 'download_property_portals'

    Mode: RAW SALES DUMP
    - Do NOT ask for neighborhood; operation is fixed to 'venta'.
    - Do NOT filter listings online (no LLM filter here).
    - Scrape everything found on Zonaprop and save it to a file as-is.
    - No regex, no keyword heuristics anywhere in this class.
    """

    name = "download_property_portals"

    def __init__(self, logger, model_name: str = "gpt-4o-mini", temperature: float = 0.0):
        super().__init__(logger)

        # Kept for future compatibility; not used in this "raw dump" mode.
        self._llm_filter_calls = 0
        self.llm = ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        # Prompts retained for interface compatibility (NOT used).
        self.extract_prompt = ChatPromptTemplate.from_messages([
            ("system", "Deprecated in RAW mode: no slot extraction is performed."),
            ("user", "Ignored.")
        ])
        self.reprompt_prompt = ChatPromptTemplate.from_messages([
            ("system", "Deprecated in RAW mode: no reprompt is needed."),
            ("user", "Ignored.")
        ])
        self.listing_filter_prompt = ChatPromptTemplate.from_messages([
            ("system", "Deprecated in RAW mode: no online LLM filtering."),
            ("user", "Ignored.")
        ])

    # --- Google Drive upload helper (service account) ---
    def _upload_to_drive(self, file_path: str) -> str:
        """Sube a Drive (Shared Drive) usando credenciales en <root>/config."""


        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")

        # <root>/config
        root_dir = Path.cwd()
        config_dir = root_dir / "config"

        client_json = config_dir / "client_secret_186464463107-ga6pk2655frmkq18o9rih98uvfh7am9.apps.googleusercontent.com.json"
        token_file = config_dir / "token.json"

        folder_id = "1hJOsSgUqdtSKs2DtEg7rMAN9yhNWMqVE"
        scopes = ["https://www.googleapis.com/auth/drive.file"]

        creds = None
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), scopes)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(client_json), scopes)
                creds = flow.run_local_server(port=0)
            token_file.write_text(creds.to_json(), encoding="utf-8")

        drive = build("drive", "v3", credentials=creds)

        meta = {"name": p.name, "parents": [folder_id]}
        media = MediaFileUpload(str(p), resumable=True)

        f = drive.files().create(
            body=meta,
            media_body=media,
            fields="id,webViewLink",
            supportsAllDrives=True,
        ).execute()

        drive.permissions().create(
            fileId=f["id"],
            body={"role": "reader", "type": "anyone"},
            supportsAllDrives=True,
        ).execute()

        return f["webViewLink"]

    # ------------------- Required slots -------------------

    def required_slots(self) -> Dict[str, str]:
        """
        RAW mode requires no slots. We won't ask the user anything.
        """
        return {}

    # ------------------- Slot extraction -------------------

    def try_extract(self, user_text: str) -> Dict[str, str]:
        """
        RAW mode: skip extraction entirely; operation is fixed to 'venta'.
        """
        self.logger.info("[extract] Skipped (RAW sales dump; no neighborhood, fixed 'venta').")
        return {}

    # ------------------- Reprompt builder -------------------

    def build_prompt_for_missing(self, missing: Dict[str, str], user_text: Optional[str] = None) -> str:
        """
        RAW mode: never reprompt because there are no required slots.
        """
        self.logger.info("[reprompt] Skipped (no required slots in RAW mode).")
        return ""

    # ------------------- LLM validator (BYPASS) -------------------

    def _llm_keep_listing(self, listing: ZpListing, target: str) -> bool:
        # BYPASS validator: keep everything (RAW mode)
        return True

    # ------------------- Execute -------------------

    def _dedupe_cross_portal(self, items: list[ZpListing]) -> list[ZpListing]:
        """
        Cross-portal dedupe using listing.canonical_key().
        Keeps the first occurrence (stable order). Portal/source remains visible.
        """
        seen = set()
        out = []
        for it in items:
            key = it.canonical_key()
            if not key:
                # fallback: keep unique by (source,id)
                key = f"{it.source}:{it.id}"
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    def _export_txt_combined(self, barrio: str, operacion: str, listings: list[ZpListing]) -> str:
        """
        Single TXT export (sync, no async Path). Returns the absolute path as str.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        fname = f"{barrio.replace(' ', '_')}_{operacion}_ALLPORTALS_{ts}.txt"
        outdir = "exports"
        os.makedirs(outdir, exist_ok=True)
        fpath = os.path.join(outdir, fname)

        pages_zp = getattr(self, "_zp_pages_scanned", None)
        pages_ap = getattr(self, "_ap_pages_scanned", None)

        lines = [f"# Combined — {barrio.title()} ({operacion}) — {ts}"]
        if pages_zp is not None:
            lines.append(f"# Zonaprop pages scanned: {pages_zp}")
        if pages_ap is not None:
            lines.append(f"# Argenprop pages scanned: {pages_ap}")
        lines.append("")

        for i, it in enumerate(listings, 1):
            lines.append(f"## {i}. {it.title or '(no title)'}")
            if it.price:    lines.append(f"- Precio: {it.price}")
            if it.location: lines.append(f"- Ubicación: {it.location}")
            if it.details:  lines.append(f"- Detalles: {it.details}")
            if it.agency:   lines.append(f"- Agencia: {it.agency}")
            lines.append(f"- Portal: {it.source}")
            lines.append(f"- URL: {it.url}")
            lines.append("")

        with open(fpath, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        return fpath

    def execute(self, filled_slots: Dict[str, str]) -> str:
        """
        RAW multi-portal download:
        - neighborhood = "" (ALL CABA)
        - operation = "venta"
        - Scrapes Zonaprop + Argenprop (AP is experimental)
        - Cross-portal dedupe
        - Single combined TXT with source marker
        - Upload final file to transfer.sh and return public URL
        """
        import time
        import os
        from pathlib import Path

        t0 = time.monotonic()
        neighborhood = ""  # ALL CABA
        operation = "venta"

        self.logger.info("[exec] RAW combined start: op=%s, barrio=<ALL CABA>", operation)

        # 1) Zonaprop (no export)
        zp = DownloadZonapropPropertyDemo(
            logger=self.logger,
            listing_validator=self._llm_keep_listing,
        )
        r1 = zp.run(neighborhood, operation, export=False)
        zp_list = r1.get("listings", []) if r1.get("ok") else []
        zp_pages = getattr(zp, "_pages_scanned", None)

        # 2) Argenprop (no export) — experimental
        ap = DownloadArgenpropPropertyDemo(
            logger=self.logger,
            listing_validator=self._llm_keep_listing,
        )
        r2 = ap.run(neighborhood, operation, export=False)
        ap_list = r2.get("listings", []) if r2.get("ok") else []
        ap_pages = getattr(ap, "_pages_scanned", None)

        # 3) Merge + cross-portal dedupe
        merged = zp_list + ap_list
        deduped = self._dedupe_cross_portal(merged)

        # 4) Export single combined file
        out_path = self._export_txt_combined("caba", operation, deduped)

        # 5) Upload to Google Drive (public link)
        try:
            public_url = self._upload_to_drive(out_path)
            download_line = f"\n📂 Link: {public_url}"
        except Exception as ex:
            self.logger.warning("drive_upload_failed", extra={"error": str(ex)})
            download_line = "\n⚠️ Falló la subida a Drive"

        return (
            f"✅ Descarga completada\n"
            f"• Zonaprop: {len(zp_list)} avisos (páginas: {zp_pages or '-'})\n"
            f"• Argenprop: {len(ap_list)} avisos (páginas: {ap_pages or '-'})\n"
            f"• Únicos (dedupe): {len(deduped)}\n"
            f"• Archivo: {Path(out_path).name}{download_line}"
        )


