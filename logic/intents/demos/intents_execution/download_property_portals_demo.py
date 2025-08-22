# logic/intents/demos/download_property_portals_demo.py
from __future__ import annotations

import json
from typing import Dict, Optional

from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

from logic.intents.base_intent_logic_demo import BaseIntentLogicDemo
from logic.intents.demos.intents_execution.download_zonaprop_property_demo import (
    DownloadZonapropPropertyDemo, ZpListing
)


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
        """
        BYPASS validator: keep EVERY listing.
        - No regex, no heuristics, no LLM call here.
        - Returns True unconditionally to dump everything to file.
        """
        return True

    # ------------------- Execute -------------------

    def execute(self, filled_slots: Dict[str, str]) -> str:
        """
        Execute the RAW download:
        - neighborhood = "" (all CABA)
        - operation = "venta" (fixed)
        - Connects to DownloadZonapropPropertyDemo and dumps EVERYTHING found.
        """
        import time, os
        t0 = time.monotonic()

        neighborhood = ""       # all barrios
        operation = "venta"     # fixed to sales

        self.logger.info("[exec] RAW dump start: op=%s, barrio=<ALL CABA>", operation)

        try:
            scraper = DownloadZonapropPropertyDemo(
                logger=self.logger,
                # Pass BYPASS validator to avoid discarding anything
                listing_validator=self._llm_keep_listing,
            )

            # NOTE: run(neighborhood, operation) must accept empty neighborhood for "all".
            res = scraper.run(neighborhood, operation)

            self.logger.info(
                "[exec] scraper_done ok=%s count=%s file=%s elapsed=%.2fs llm_calls=%d",
                res.get("ok"), res.get("count"), res.get("file"),
                time.monotonic() - t0, self._llm_filter_calls
            )

            if not res.get("ok"):
                return f"⚠️ Could not download: {res.get('message', 'Unknown error')}"

            path = res["file"]
            try:
                size = os.path.getsize(path)
                self.logger.info("[exec] file_ready path=%s size=%dB", path, size)
            except Exception as e:
                self.logger.warning("[exec] file_stat_error path=%s err=%s", path, e)

            return (
                f"✅ Downloaded {res['count']} *venta* listings in *CABA (all barrios)* "
                f"(Zonaprop — RAW, unfiltered dump).\nFile: {path}"
            )

        except Exception as ex:
            self.logger.exception("[exec] EXC during RAW dump: op=%s", operation)
            return "❌ An error occurred during download. Please try again later."
