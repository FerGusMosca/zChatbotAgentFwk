import re
from typing import Optional

class IntentDetectionCompetitionFile:
    """Detects user intent to retrieve competition files (Q10 or K10 curated reports)."""

    Q10_base_folder = "Q10_competition_summary_report"
    K10_base_folder = "K10_competition_summary_report"

    def __init__(self, logger=None):
        self.logger = logger

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text to uppercase and remove accents for easier regex matching."""
        return (
            text.upper()
            .replace("Á", "A")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ú", "U")
        )

    def detect(self, question: str) -> Optional[str]:
        """
        Detects symbol, report type (Q10/K10), year, and period from the user's question.
        Returns relative path to the competition file if all required fields are found.
        """
        text = self._normalize(question)

        # --- SYMBOL detection (more strict)
        sym_match = re.search(r'\b(?:DE|DEL|DE LA|SYMBOL)\s+([A-Z]{1,6})\b', text)
        if not sym_match:
            all_syms = re.findall(r'\b[A-Z]{2,6}\b', text)
            symbol = all_syms[-1] if all_syms else None
        else:
            symbol = sym_match.group(1)
        if symbol:
            symbol = symbol.strip().upper()

        # --- REPORT TYPE detection
        rpt_match = re.search(r'\b(K10|Q10|10K|10Q)\b', text)
        if rpt_match:
            report_type = rpt_match.group(1).upper()
        else:
            if "ANUAL" in text:
                report_type = "K10"
            elif "TRIMESTRAL" in text or "Q" in text:
                report_type = "Q10"
            else:
                report_type = None

        # --- YEAR detection
        year_match = re.search(r'(20\d{2})', text)
        year = year_match.group(1) if year_match else None

        # --- PERIOD detection
        period_match = re.search(r'\b(Q[1-4]|ANUAL|Y20\d{2})\b', text)
        if period_match:
            val = period_match.group(1).upper()
            period = f"Y{year}" if val == "ANUAL" else val
        elif report_type == "K10" and year:
            period = f"Y{year}"
        else:
            period = None

        # --- Logging for debugging
        if self.logger:
            self.logger.info(
                f"[IntentDetection] Fields detected → symbol={symbol}, type={report_type}, year={year}, period={period}"
            )

        # --- Validation
        if not all([symbol, report_type, year, period]):
            if self.logger:
                self.logger.warning(
                    f"[IntentDetection] ❌ Missing fields → symbol={symbol}, type={report_type}, year={year}, period={period}"
                )
            return None

        # --- Folder selection ---
        folder = (
            self.K10_base_folder if report_type in ("K10", "10K") else self.Q10_base_folder
        )
        from pathlib import Path
        path = str(Path(folder) / year / f"{symbol}_{year}_{period}_competition.json")

        if self.logger:
            self.logger.info(f"[IntentDetection] ✅ Path resolved: {path}")

        return path
