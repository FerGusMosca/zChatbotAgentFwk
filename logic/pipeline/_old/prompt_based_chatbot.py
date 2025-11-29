import os

from openai import OpenAI

'''
class PromptBasedChatbot:
    def __init__(self, prompt_loader, prompt_name="generic_prompt"):
        self.prompt_loader = prompt_loader
        self.prompt_name = prompt_name
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.system_prompt = self.prompt_loader.get_prompt(prompt_name)

    def handle(self, user_query: str) -> str:
        base_prompt = self.system_prompt

        # Simulated semantic search
        retrieved_docs = [""]

        if not retrieved_docs[0].strip():
            print("[DEBUG] No relevant context found. Escalating to OpenAI.")
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": base_prompt},
                    {"role": "user", "content": user_query}
                ]
            )
            return response.choices[0].message.content

        # Si sí hay contexto:
        return f"{base_prompt}\n\nContext:\n{retrieved_docs[0]}\n\nQuestion: {user_query}\nAnswer:"

'''