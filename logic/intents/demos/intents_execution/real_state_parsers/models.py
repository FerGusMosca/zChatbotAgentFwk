# comments in English only
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import re

@dataclass
class ZpListing:
    id: str                 # internal unique id (prefix + portal_id or URL)
    url: str
    title: Optional[str]
    price: Optional[str]
    location: Optional[str]
    details: Optional[str]
    agency: Optional[str]
    source: str             # "zonaprop" | "argenprop"
    portal_id: Optional[str] = None

    def canonical_key(self) -> str:
        """
        Cross-portal dedupe key using normalized (location + title + details + numeric price).
        Excludes URL to allow cross-portal matches.
        """
        def norm(s: Optional[str]) -> str:
            if not s:
                return ""
            s = s.lower()
            s = re.sub(r"\s+", " ", s)
            s = re.sub(r"[^\w\s\-\.\,]", "", s)
            return s.strip()

        price_digits = re.sub(r"[^\d]", "", self.price or "")[:8]
        key = " | ".join([norm(self.location), norm(self.title), norm(self.details), price_digits])
        return re.sub(r"\s+", " ", key)
