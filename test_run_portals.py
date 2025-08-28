# test_run_portals.py
import logging

from logic.intents.demos.intents_execution.download_property_portals_demo import DownloadPropertyPortalsIntentLogicDemo


def build_logger() -> logging.Logger:
    lg = logging.getLogger("portals_test")
    lg.setLevel(logging.INFO)
    if not lg.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        lg.addHandler(h)
    return lg

if __name__ == "__main__":
    logger = build_logger()
    demo = DownloadPropertyPortalsIntentLogicDemo(logger=logger, use_llm=False)

    # No slots needed in RAW mode
    summary = demo.execute({})
    print(summary)
    print("Revisá la carpeta 'exports/': deberías ver el TXT combinado y los dumps en exports/debug/.")
