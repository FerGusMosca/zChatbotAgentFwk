# logic/intents/demos/download_property_portals_demo.py
from __future__ import annotations
from datetime import datetime
from typing import Dict, Optional
import os
from pathlib import Path

from common.util.uploader.google_drive_upload import GoogleDriveUpload
from logic.intents.base_intent_logic_demo import BaseIntentLogicDemo
from logic.intents.demos.intents_execution.real_state_parsers.download_argenprop_property_demo import (
    DownloadArgenpropPropertyDemo,
)
from logic.intents.demos.intents_execution.real_state_parsers.download_zonaprop_property_demo import (
    DownloadZonapropPropertyDemo,
)
from logic.intents.demos.intents_execution.real_state_parsers.models import ZpListing

# Optional LLM (not used when use_llm=False)
try:
    from langchain_community.chat_models import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate
except Exception:
    ChatOpenAI = None
    ChatPromptTemplate = None

# Google Drive uploader utility (our wrapper)



class DownloadPropertyPortalsIntentLogicDemo(BaseIntentLogicDemo):
    """
    Intent: 'download_property_portals'

    RAW SALES DUMP:
      - Fixed barrio: "" (ALL CABA)
      - Fixed operation: 'venta'
      - No slot extraction or online LLM filtering when use_llm=False
      - Runs Zonaprop + Argenprop scrapers, merges, deduplicates
      - Exports a single TXT to /exports
      - Optional upload to Google Drive via GoogleDriveUpload helper
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
        export_dir: str = "exports",
    ):
        super().__init__(logger)
        self.use_llm = use_llm
        self.upload_to_drive = upload_to_drive
        self.drive_folder_id = drive_folder_id  # must be provided if upload_to_drive=True
        self.export_dir = export_dir

        self._llm_filter_calls = 0
        self._zp_pages_scanned: Optional[int] = None
        self._ap_pages_scanned: Optional[int] = None

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

    # -------- Google Drive upload (optional) --------
    # dentro de DownloadPropertyPortalsIntentLogicDemo

    def _upload_to_drive(self, file_path: str) -> str:
        """
        Upload the combined TXT to Google Drive using GoogleDriveUpload.
        Logs EVERY path we try to read so you see exactly what is happening.
        """
        from pathlib import Path
        from common.util.settings.env_deploy_reader import EnvDeployReader
        from common.util.uploader.google_drive_upload import GoogleDriveUpload

        if not self.upload_to_drive:
            raise RuntimeError("Drive upload disabled (set upload_to_drive=True).")

        # ---- Read .env_deploy (and trim whitespace) ----
        folder_id = (EnvDeployReader.get("DRIVE_FOLDER_ID", self.drive_folder_id or "") or "").strip()
        client_secret_name = (EnvDeployReader.get("GOOGLE_CLIENT_SECRET", "") or "").strip()
        token_name = (EnvDeployReader.get("GOOGLE_TOKEN_FILE", "token.json") or "").strip()

        # ---- Discover ./config robustly (supports running from subfolders) ----
        def find_config_dir(start: Path) -> Path:
            for p in [start, *start.parents]:
                cand = p / "config"
                if cand.exists():
                    return cand
            return start / "config"

        cwd = Path.cwd()
        config_dir = find_config_dir(cwd)

        # ---- Candidate paths (explicit + fallback glob) ----
        explicit_client = (config_dir / client_secret_name) if client_secret_name else None
        explicit_exists = explicit_client.exists() if explicit_client else False

        # Logs so we SEE exactly what we try to read
        self.logger.info("[drive.find] cwd=%r", str(cwd))
        self.logger.info("[drive.find] config_dir=%r exists=%s", str(config_dir), config_dir.exists())
        self.logger.info("[drive.find] explicit_client_secret=%r exists=%s",
                         str(explicit_client) if explicit_client else "<none>", explicit_exists)

        if not explicit_client or not explicit_exists:
            hit = next(config_dir.glob("client_secret*.json"), None)
            self.logger.info("[drive.find] fallback_glob='client_secret*.json' hit=%r",
                             str(hit) if hit else "<none>")
            client_path = hit
        else:
            client_path = explicit_client

        token_path = config_dir / (token_name or "token.json")
        self.logger.info("[drive.find] token_path=%r exists=%s", str(token_path), token_path.exists())

        # Final sanity + what we will use
        self.logger.info("[drive.cfg] folder_id_tail=%s file_to_upload=%r",
                         (folder_id or "")[-10:], str(file_path))

        if not folder_id:
            raise ValueError("DRIVE_FOLDER_ID is empty (set it in .env_deploy or pass drive_folder_id).")
        if not client_path or not client_path.exists():
            raise FileNotFoundError(f"Google client secret not found: {client_path!r}")

        # ---- Upload ----
        uploader = GoogleDriveUpload(
            client_secret_path=client_path,
            token_path=token_path,
        )
        self.logger.info("[drive.upload] using client_secret=%r token=%r",
                         str(client_path), str(token_path))
        link = uploader.upload_file(file_path, folder_id=folder_id)
        self.logger.info("[drive.done] webViewLink=%s", link)
        return link

    # -------- Slots / reprompt (no-op in RAW mode) --------
    def required_slots(self) -> Dict[str, str]:
        return {}

    def try_extract(self, user_text: str) -> Dict[str, str]:
        self.logger.info("[extract] Skipped (RAW sales dump; fixed 'venta', barrio='').")
        return {}

    def build_prompt_for_missing(self, missing: Dict[str, str], user_text: Optional[str] = None) -> str:
        self.logger.info("[reprompt] Skipped (no required slots in RAW mode).")
        return ""

    # -------- Keep-all validator (RAW) --------
    def _llm_keep_listing(self, listing: ZpListing, target: str) -> bool:
        return True

    # -------- Cross-portal dedupe --------
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

    # -------- TXT export --------
    def _export_txt_combined(self, barrio: str, operacion: str, listings: list[ZpListing]) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        fname = f"{barrio.replace(' ', '_')}_{operacion}_ALLPORTALS_{ts}.txt"

        os.makedirs(self.export_dir, exist_ok=True)
        fpath = os.path.join(self.export_dir, fname)

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

    # -------- Execute --------
    def execute(self, filled_slots: Dict[str, str]) -> str:
        import time
        t0 = time.monotonic()
        neighborhood = ""   # ALL CABA
        operation = "venta" # fixed for RAW dump

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
                download_line = "\n⚠️ Drive upload failed"
        else:
            download_line = "\n(Drive upload disabled)"

        dt = time.monotonic() - t0
        return (
            f"✅ Download completed ({dt:.1f}s)\n"
            f"• Zonaprop: {len(zp_list)} listings (pages: {self._zp_pages_scanned or '-'})\n"
            f"• Argenprop: {len(ap_list)} listings (pages: {self._ap_pages_scanned or '-'})\n"
            f"• Unique (deduped): {len(deduped)}\n"
            f"• File: {Path(out_path).name}{download_line}"
        )
