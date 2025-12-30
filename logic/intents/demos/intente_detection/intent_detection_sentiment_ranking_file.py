import re
from typing import Optional

class SentimentRankingFileDetection:
    """
    Robust detection for K10 / Q10 sentiment ranking files.
    Always returns a path RELATIVE to the profile, starting with:
    - K10_sentiment_summary_report_rank/{year}/sentiment_summary_ranking_{year}.csv
    - Q10_sentiment_summary_report_rank/{year}/sentiment_summary_ranking_{year}.csv
    """

    K10_rank_folder = "K10_sentiment_summary_report_rank"
    Q10_rank_folder = "Q10_sentiment_summary_report_Q{quarter}_rank"
    K10_report="K10"
    Q10_report="Q10"

    def __init__(self, logger=None):
        self.logger = logger

    @staticmethod
    def _normalize(text: str) -> str:
        return (
            text.upper()
            .replace("Á", "A")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ú", "U")
        )

    def detect(self, question: str) -> Optional[str]:

        if self.logger:
            self.logger.info("[SRFD] Raw question received.")
            self.logger.info(f"[SRFD] question={question}")

        txt = self._normalize(question)

        if self.logger:
            self.logger.info(f"[SRFD] Normalized={txt}")

        # ------------------------------------------------------------
        # REPORT TYPE
        # ------------------------------------------------------------
        rpt = None
        quarter=None
        if re.search(r"\b(K10|10K|10-K|ANUAL|FORM\s*K)\b", txt):
            rpt = self.K10_report
        elif re.search(r"\b(Q10|10Q|10-Q|TRIMESTRAL|FORM\s*Q)\b", txt):
            rpt = self.Q10_report
            qm = re.search(r"\bQ([1-4])\b", txt)
            quarter = qm.group(1) if qm else None

            if not quarter:
                if self.logger:
                    self.logger.warning("[SRFD] ❌ Q10 detected but no quarter found.")
                return None

        if self.logger:
            self.logger.info(f"[SRFD] Detected report_type={rpt}")

        if not rpt:
            if self.logger:
                self.logger.warning("[SRFD] ❌ No report type detected.")
            return None

        # ------------------------------------------------------------
        # YEAR
        # ------------------------------------------------------------
        m = re.search(r"(20\d{2})", txt)
        year = m.group(1) if m else None

        if self.logger:
            self.logger.info(f"[SRFD] Detected year={year}")

        if not year:
            if self.logger:
                self.logger.warning("[SRFD] ❌ No year detected.")
            return None

        # ------------------------------------------------------------
        # FOLDER
        # ------------------------------------------------------------
        if rpt == self.K10_report:
            folder = self.K10_rank_folder
        elif rpt==self.Q10_report:
            folder = self.Q10_rank_folder.replace("{quarter}", quarter)
        else:
            raise  Exception(f"Invalid report type {rpt}")

        if self.logger:
            self.logger.info(f"[SRFD] Selected folder={folder}")

        # ------------------------------------------------------------
        # FINAL PATH  **USANDO SLASHES**
        # ------------------------------------------------------------
        final_path = f"{folder}/{year}/sentiment_summary_ranking_{year}.csv"

        if self.logger:
            self.logger.info(f"[SRFD] ✅ Final resolved CSV path: {final_path}")

        return final_path
