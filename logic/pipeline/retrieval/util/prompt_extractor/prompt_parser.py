# common/util/prompt_parser.py
import re
from typing import Dict

class PromptSectionExtractor:
    @staticmethod
    def extract(prompt: str, section: str) -> str:
        match = re.search(rf"\[{section}\](.*?)(?=\n\[|\Z)", prompt, re.DOTALL)
        return match.group(0).strip() if match else ""

    @staticmethod
    def all_sections(prompt: str) -> Dict[str, str]:
        return {
            m.group(1): m.group(2).strip()
            for m in re.finditer(r"\[([^\]]+)\](.*?)(?=\n\[|\Z)", prompt, re.DOTALL)
        }