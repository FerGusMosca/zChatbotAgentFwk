# logic/intents/demos/download_property_portals_demo.py
from __future__ import annotations
from datetime import datetime
from typing import Dict, Optional
import os
from pathlib import Path

from logic.intents.base_intent_logic_demo import BaseIntentLogicDemo
from logic.intents.demos.intents_execution.real_state_parsers.download_argenprop_property_demo import (
    DownloadArgenpropPropertyDemo,
)
from logic.intents.demos.intents_execution.real_state_parsers.download_zonaprop_property_demo import (
    DownloadZonapropPropertyDemo,
)
from logic.intents.demos.intents_execution.real_state_parsers.models import ZpListing

# Opcional LLM (no se usa cuando use_llm=False)
try:
    from langchain_community.chat_models import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate
except Exception:
    ChatOpenAI = None
    ChatPromptTemplate = None

# Opcional Drive
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
except Exception:
    build = None
    MediaFileUpload = None
    Credentials = None
    InstalledAppFlow = None
    Request = None


class DownloadPropertyPortalsIntentLogicDemo(BaseIntentLogicDemo):
    """
    Intent: 'download_property_portals'

    RAW SALES DUMP
    - Barrio fijo: "" (CABA completa)
    - Operación: 'venta'
    - No hay extracción de slots ni filtro por LLM cuando use_llm=False
    - Ejecuta Zonaprop + Argenprop, mergea, dedup y escribe un único TXT en /exports
    - Subida a Drive opcional
    """

    name = "download_property_portals"

    def __init__(
        self,
        logger,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        use_llm: bool = False,
        *,
        upload_to_drive: bool = False,
        drive_folder_id: Optional[str] = None,
    ):
        super().__init__(logger)
        self.use_llm = use_llm
        self.upload_to_drive = upload_to_drive
        self.drive_folder_id = drive_folder_id  # si es None y upload_to_drive=True -> error controlado

        self._llm_filter_calls = 0

        if self.use_llm and ChatOpenAI is not None:
            self.llm = ChatOpenAI(
                model_name=model_name,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            self.extract_prompt = ChatPromptTemplate.from_messages(
                [("system", "RAW mode: not used"), ("user", "Ignored.")]
            )
            self.reprompt_prompt = ChatPromptTemplate.from_messages(
                [("system", "RAW mode: not used"), ("user", "Ignored.")]
            )
            self.listing_filter_prompt = ChatPromptTemplate.from_messages(
                [("system", "RAW mode: not used"), ("user", "Ignored.")]
            )
        else:
            self.llm = None
            self.extract_prompt = None
            self.reprompt_prompt = None
            self.listing_filter_prompt = None

        # para cabecera del TXT combinado
        self._zp_pages_scanned: Optional[int] = None
        self._ap_pages_scanned: Optional[int] = None

    # -------- Google Drive (opcional) --------
    def _upload_to_drive(self, file_path: str) -> str:
        if not self.upload_to_drive:
            raise RuntimeError("Drive upload disabled (set upload_to_drive=True to enable).")
        if build is None:
            raise RuntimeError("Google Drive libraries not available in this environment.")
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")

        # config files en <root>/config
        root_dir = Path.cwd()
        config_dir = root_dir / "config"
        client_json = next(config_dir.glob("client_secret*.json"), None)
        token_file = config_dir / "token.json"

        if not client_json:
            raise FileNotFoundError("Google client_secret*.json not found in ./config")

        folder_id = self.drive_folder_id or ""
        if not folder_id:
            raise ValueError("drive_folder_id is empty; provide a Shared Drive folder id.")

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

    # -------- RAW slots/reprompt (no-op) --------
    def required_slots(self) -> Dict[str, str]:
        return {}

    def try_extract(self, user_text: str) -> Dict[str, str]:
        self.logger.info("[extract] Skipped (RAW sales dump; fixed 'venta', barrio='').")
        return {}

    def build_prompt_for_missing(self, missing: Dict[str, str], user_text: Optional[str] = None) -> str:
        self.logger.info("[reprompt] Skipped (no required slots in RAW mode).")
        return ""

    # -------- Validator (bypass) --------
    def _llm_keep_listing(self, listing: ZpListing, target: str) -> bool:
        return True

    # -------- Dedupe --------
    def _dedupe_cross_portal(self, items: list[ZpListing]) -> list[ZpListing]:
        seen = set()
        out = []
        for it in items:
            key = it.canonical_key() or f"{it.source}:{it.id}"
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    # -------- TXT combinado --------
    def _export_txt_combined(self, barrio: str, operacion: str, listings: list[ZpListing]) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        fname = f"{barrio.replace(' ', '_')}_{operacion}_ALLPORTALS_{ts}.txt"
        outdir = "exports"
        os.makedirs(outdir, exist_ok=True)
        fpath = os.path.join(outdir, fname)

        lines = [f"# Combined — {barrio.title()} ({operacion}) — {ts}"]
        if self._zp_pages_scanned is not None:
            lines.append(f"# Zonaprop pages scanned: {self._zp_pages_scanned}")
        if self._ap_pages_scanned is not None:
            lines.append(f"# Argenprop pages scanned: {self._ap_pages_scanned}")
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

        Path(fpath).write_text("\n".join(lines), encoding="utf-8")
        return fpath

    # -------- Ejecutar --------
    def execute(self, filled_slots: Dict[str, str]) -> str:
        import time
        t0 = time.monotonic()
        neighborhood = ""  # ALL CABA
        operation = "venta"

        self.logger.info("[exec] RAW combined start: op=%s, barrio=<ALL CABA>", operation)

        # 1) Zonaprop
        zp_list = []
        try:
            zp = DownloadZonapropPropertyDemo(
                logger=self.logger,
                listing_validator=self._llm_keep_listing,
            )
            r1 = zp.run(neighborhood, operation, export=False)
            zp_list = r1.get("listings", []) if r1.get("ok") else []
            self._zp_pages_scanned = getattr(zp, "_pages_scanned", None)
            self.logger.info("[zp] ok=%s count=%s pages=%s", r1.get("ok"), len(zp_list), self._zp_pages_scanned)
        except Exception as ex:
            self.logger.exception("[zp] error: %s", ex)

        # 2) Argenprop
        ap_list = []
        try:
            ap = DownloadArgenpropPropertyDemo(
                logger=self.logger,
                listing_validator=self._llm_keep_listing,
            )
            r2 = ap.run(neighborhood, operation, export=False)
            ap_list = r2.get("listings", []) if r2.get("ok") else []
            self._ap_pages_scanned = getattr(ap, "_pages_scanned", None)
            self.logger.info("[ap] ok=%s count=%s pages=%s", r2.get("ok"), len(ap_list), self._ap_pages_scanned)
        except Exception as ex:
            self.logger.exception("[ap] error: %s", ex)

        # 3) Merge + dedupe
        merged = zp_list + ap_list
        deduped = self._dedupe_cross_portal(merged)
        self.logger.info("[merge] zp=%d ap=%d deduped=%d", len(zp_list), len(ap_list), len(deduped))

        # 4) Export
        out_path = self._export_txt_combined("caba", operation, deduped)

        # 5) Upload (optional)
        if self.upload_to_drive:
            try:
                public_url = self._upload_to_drive(out_path)
                download_line = f"\n📂 Link: {public_url}"
            except Exception as ex:
                self.logger.warning("drive_upload_failed | %s", ex)
                download_line = "\n⚠️ Falló la subida a Drive"
        else:
            download_line = "\n(Drive upload disabled)"

        dt = time.monotonic() - t0
        return (
            f"✅ Descarga completada ({dt:.1f}s)\n"
            f"• Zonaprop: {len(zp_list)} avisos (páginas: {self._zp_pages_scanned or '-'})\n"
            f"• Argenprop: {len(ap_list)} avisos (páginas: {self._ap_pages_scanned or '-'})\n"
            f"• Únicos (dedupe): {len(deduped)}\n"
            f"• Archivo: {Path(out_path).name}{download_line}"
        )
