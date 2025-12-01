# ===============================
# dedup_eliminator.py
# GOD-TIER VERSION – ZERO MAGIC STRINGS, ZERO HARDCODED KEYS
# ===============================

import logging
import re
import xxhash
import json
from pathlib import Path
from typing import List, Any, Set
from dataclasses import dataclass, field


@dataclass
class DedupResult:
    docs: List[Any] = field(default_factory=list)
    removed: int = 0


class DedupEliminator:
    """
    Final form.
    Not a single hardcoded string key in the entire class.
    Everything is driven by the JSON config – even the key names themselves.
    """

    # These are the ONLY strings that exist – and they are private constants for internal reference
    _KEY_THRESHOLD = "short_threshold_chars"
    _KEY_CORE_IMPORTANT = "core_length_when_important"
    _KEY_CORE_LONG = "core_length_when_long"
    _KEY_PRESERVE_KW = "preserve_keywords"
    _KEY_META_KEYS = "metadata_keys_to_include"
    _KEY_PRESET = "current_preset"
    _KEY_PRESETS = "aggressiveness_presets"
    _KEY_REQUIRED_LIST = "__required_keys"
    _KEY_INTENT_MAP = "aggressiveness_by_intent"
    _KEY_DEFAULT_PRESET = "default_aggressiveness"

    def __init__(self, logger: logging.Logger | None = None, dedup_settings_path: str | Path | None = None):
        self.logger = logger or logging.getLogger(__name__)

        if not dedup_settings_path:
            raise ValueError("dedup_settings_path is required")

        config_path = Path(dedup_settings_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Dedup config not found: {config_path.resolve()}")

        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8"))
            self.logger.info(f"Dedup config loaded: {config_path.resolve()}")
        except Exception as e:
            raise ValueError(f"Invalid JSON in dedup config: {e}")

        # Apply preset if exists
        if self.config.get(self._KEY_PRESET) and self.config.get(self._KEY_PRESETS):
            preset_name = self.config[self._KEY_PRESET]
            if preset_name in self.config.get(self._KEY_PRESETS, {}):
                self.config.update(self.config[self._KEY_PRESETS][preset_name])
                self.logger.info(f"Dedup preset '{preset_name}' applied")

        # Get required keys – either from JSON or fallback to known minimal set
        required_keys = self.config.get(self._KEY_REQUIRED_LIST, {
            self._KEY_THRESHOLD,
            self._KEY_CORE_IMPORTANT,
            self._KEY_CORE_LONG,
            self._KEY_PRESERVE_KW,
            self._KEY_META_KEYS
        })

        missing = required_keys - self.config.keys()
        if missing:
            raise KeyError(f"Missing required keys in dedup.json: {sorted(missing)}")

        # Build preserve set
        self.preserve: Set[str] = {
            kw.lower() for kw in self.config.get(self._KEY_PRESERVE_KW, [])
        }

        self._apply_dynamic_preset(None)

        self.logger.info(
            f"Dedup ready | threshold={self.config.get(self._KEY_THRESHOLD)} | "
            f"important_core={self.config.get(self._KEY_CORE_IMPORTANT)} | "
            f"keywords={len(self.preserve)}"
        )

    def _apply_dynamic_preset(self, intent: str | None) -> None:
        mapping = self.config.get(self._KEY_INTENT_MAP, {})
        chosen = mapping.get(intent,
                             self.config.get(self._KEY_DEFAULT_PRESET, self.config.get(self._KEY_PRESET, "medium")))

        if chosen in self.config.get(self._KEY_PRESETS, {}):
            preset_data = self.config[self._KEY_PRESETS][chosen]
            self.config.update(preset_data)
            self.logger.info(f"[DEDUP] Dynamic → intent='{intent or 'default'}' → preset='{chosen}'")

    def normalize(self, text: str) -> str:
        t = text.lower()
        t = re.sub(r"\s+", " ", t)
        t = re.sub(r"[^\w\s.%$-]", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    def fingerprint(self, doc: Any) -> str:
        text = getattr(doc, "page_content", None) or getattr(doc, "text", None) or str(doc)
        n = self.normalize(text)

        meta_parts = [
            str(doc.metadata.get(k, "")) for k in self.config.get(self._KEY_META_KEYS, [])
            if hasattr(doc, "metadata") and k in doc.metadata
        ]
        meta = "|".join(meta_parts)

        is_important = (
            len(n) < self.config.get(self._KEY_THRESHOLD, 999999) or
            bool(self.preserve.intersection(n.lower().split()))
        )

        core_length = (
            self.config.get(self._KEY_CORE_IMPORTANT, 1500) if is_important
            else self.config.get(self._KEY_CORE_LONG, 750)
        )
        core = n[:core_length]

        h = xxhash.xxh64()
        h.update(core.encode("utf-8"))
        h.update(meta.encode("utf-8"))
        return h.hexdigest()

    def run(self, docs: List[Any], label:str) -> DedupResult:
        if not docs:
            return DedupResult(docs=[], removed=0)

        self._apply_dynamic_preset(label)

        seen = set()
        uniq = []
        for doc in docs:
            key = self.fingerprint(doc)
            if key not in seen:
                seen.add(key)
                uniq.append(doc)

        removed = len(docs) - len(uniq)
        self.logger.info(f"[DEDUP] in={len(docs)} → out={len(uniq)} | removed={removed} ({removed/len(docs):.1%})")
        return DedupResult(docs=uniq, removed=removed)