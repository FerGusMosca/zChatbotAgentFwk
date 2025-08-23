from pathlib import Path
from langchain.prompts import ChatPromptTemplate


class PromptLoader:
    BASE_DIR = Path(__file__).resolve().parents[3] / "input" / "intent_prompts"

    @classmethod
    def load_prompt(cls, filename: str, role: str = "system") -> ChatPromptTemplate:
        """
        Return a ChatPromptTemplate with the file content as one message.
        By default role = 'system'.
        """
        fpath = cls.BASE_DIR / filename
        if not fpath.exists():
            raise FileNotFoundError(f"Prompt file not found: {fpath}")

        content = fpath.read_text(encoding="utf-8")
        return ChatPromptTemplate.from_messages([(role, content)])
