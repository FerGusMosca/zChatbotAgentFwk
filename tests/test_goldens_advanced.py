import json, os
import pytest
from common.util.builder.bot_engine_loader import load_hybrid_bot

# Load advanced golden cases
with open("tests/golden_advanced.json", encoding="utf-8") as f:
    GOLDENS_ADV = json.load(f)


@pytest.mark.parametrize("case", GOLDENS_ADV, ids=[c["name"] for c in GOLDENS_ADV])
def test_goldens_advanced(case):
    prompt_name = case.get("prompt_name", "")
    os.environ["ZBOT_PROMPT_NAME"] = prompt_name
    bot = load_hybrid_bot(case["client_id"], prompt_name=prompt_name, force_reload=True)

    out = bot.handle(case["question"])
    mode = bot.last_metrics["mode"]

    print(f"[GoldenAdvanced] case={case['name']} mode={mode} out={out}")

    # --- Validate mode ---
    assert mode == case["expected_mode"], \
        f"[{case['name']}] expected mode={case['expected_mode']} but got {mode}"

    # --- Validate expected_answer (single string) ---
    if "expected_answer" in case:
        assert case["expected_answer"].lower() in out.lower(), \
            f"[{case['name']}] expected_answer '{case['expected_answer']}' not in response: {out}"

    # --- Validate expected_contains (list of keywords) ---
    if "expected_contains" in case:
        for kw in case["expected_contains"]:
            assert kw.lower() in out.lower(), \
                f"[{case['name']}] missing keyword '{kw}' in response: {out}"

    # --- Validate expected_not_contains (forbidden keywords) ---
    if "expected_not_contains" in case:
        for kw in case["expected_not_contains"]:
            assert kw.lower() not in out.lower(), \
                f"[{case['name']}] forbidden keyword '{kw}' found in response: {out}"
