# test_run_argenprop_demo_min.py
"""
Minimal runner for DownloadArgenpropPropertyDemo:
- Single run (no double open)
- Writes only the class TXT export into exports/
- No CSV/JSON
- No debug dumps by default (set DUMP_DEBUG_HTML=True if needed)
"""

import logging
import sys
from pathlib import Path

# >>> Adjust import to your project structure <<<
from logic.intents.demos.intents_execution.real_state_parsers.download_argenprop_property_demo import (
    DownloadArgenpropPropertyDemo,
)

# ---------- Config ----------
OUTDIR = Path("../../exports")
BARRIO = "belgrano"           # e.g. "belgrano" or "" for CABA general
OPERACION = "venta"           # "venta" | "alquiler"
MAX_PAGES = 1
SLEEP_SECS = 0.8
HEADLESS = False              # visible tends to be friendlier
PROFILE_DIR = r"C:\Bias_Algos\APProfile"
DUMP_DEBUG_HTML = False       # keep False to avoid extra files
# ----------------------------

def accept_all_validator(listing, target: str) -> bool:
    return True

def build_logger() -> logging.Logger:
    lg = logging.getLogger("argenprop_demo_min")
    lg.setLevel(logging.INFO)
    if not lg.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        lg.addHandler(h)
    return lg

if __name__ == "__main__":
    OUTDIR.mkdir(parents=True, exist_ok=True)
    logger = build_logger()

    try:
        demo = DownloadArgenpropPropertyDemo(
            logger=logger,
            outdir=str(OUTDIR),
            max_pages=MAX_PAGES,
            sleep_secs=SLEEP_SECS,
            listing_validator=accept_all_validator,
            headless=HEADLESS,
            profile_dir=PROFILE_DIR,
            dump_debug_html=DUMP_DEBUG_HTML,
        )
    except Exception as e:
        logger.error("init.error %s", e)
        sys.exit(1)

    # Single run — class will write exactly one TXT to exports/
    try:
        logger.info("run.start barrio=%s op=%s pages=%s", BARRIO, OPERACION, MAX_PAGES)
        res = demo.run(barrio=BARRIO, operacion=OPERACION, export=True)
        if not res.get("ok"):
            logger.error("run.fail: %s", res.get("message"))
            sys.exit(2)
        txt_path = res.get("file")
        logger.info("run.ok TXT=%s count=%s", Path(txt_path).name if txt_path else None, res.get("count"))
        print(f"OK | TXT={Path(txt_path).name if txt_path else 'N/A'} | COUNT={res.get('count')}")
        # nothing else is written here on purpose
    except Exception as e:
        logger.error("run.error %s", e)
        sys.exit(3)
