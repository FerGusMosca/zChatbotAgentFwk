import os
from pathlib import Path

from common.util.std_in_out.root_locator import RootLocator


class PromptLoader:
    def __init__(self, prompt_name:str,logger):
        repo_root = RootLocator.get_root()
        prompts_path = repo_root / "prompts"
        prompt_name = prompt_name
        # prompt_loader = PromptLoader(str(prompts_path), prompt_name=prompt_name)
        self.prompts_path = prompts_path
        self.prompt_name=prompt_name
        self.prompts = {}
        self.logger=logger
        self._load_all_prompts()

    def _load_all_prompts(self):
        """Loads only the requested .txt prompt file from the given directory."""
        found = False
        for file in os.listdir(self.prompts_path):
            if file.endswith(".txt") and file.replace(".txt", "") == self.prompt_name:
                found = True
                prompt_name = file.replace(".txt", "")
                with open(os.path.join(self.prompts_path, file), "r", encoding="utf-8") as f:
                    self.prompts[prompt_name] = f.read()
                    if self.logger is not None:
                        self.logger.info(f"[PROMPT LOADER] Loaded prompt: {prompt_name} ({file}) ✅")
                    else:
                        print(f"[PROMPT LOADER] Loaded prompt: {prompt_name} ({file}) ✅")

                break

        if not found:
            raise FileNotFoundError(f"Prompt file '{self.prompt_name}.txt' not found in path '{self.prompts_path}'")

    def get_prompt(self, prompt_name: str) -> str:
        """Returns the prompt string for a given name."""
        return self.prompts.get(prompt_name, "")


    def extract_section(self,prompt_name:str, section: str) -> str:
        text=self.prompts[prompt_name]
        section_txt = PromptLoader.extract_section_from_text(text,section)
        self.logger and self.logger.info(f"{section} prompt loaded", {"length": len(section_txt)})
        return section_txt


    @staticmethod
    def extract_section_from_text( text: str, section: str) -> str:
        start = text.find(section)
        if start == -1:
            raise ValueError(f"Missing section {section} in master prompt")
        start += len(section)
        end = text.find("[", start)
        section = text[start:end if end != -1 else None].strip()
        return section
