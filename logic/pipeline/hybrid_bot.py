from typing import Optional, List, Tuple

from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.chains.llm import LLMChain
from langchain.chains.combine_documents.stuff import StuffDocumentsChain
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain_community.chat_models import ChatOpenAI

from common.util.app_logger import AppLogger


class HybridBot:
    """
    Hybrid RAG bot:
      - Tries retrieval-augmented QA when there is relevant context.
      - Falls back to a prompt-only bot otherwise.
      - Keeps conversation memory and preserves the same system prompt tone.
    """

    def __init__(
        self,
        vectordb,
        prompt_bot,
        model_name: str = "gpt-4o",
        temperature: float = 0.0,
        top_k: int = 4,
    ):
        self.retriever = vectordb.as_retriever(search_kwargs={"k": top_k})
        self.prompt_bot = prompt_bot
        self.logger = AppLogger.get_logger(__name__)
        self.top_k = top_k

        # Build a prompt = system prompt + {context} + {question}
        prompt_template = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    # Context is appended to system so the model treats it as authoritative input.
                    prompt_bot.system_prompt + "\n{context}"
                ),
                HumanMessagePromptTemplate.from_template("{question}"),
            ],
            input_variables=["context", "question"],
        )

        # Base LLM chain using the full prompt (system + context + question)
        llm_chain = LLMChain(
            llm=ChatOpenAI(model_name=model_name, temperature=temperature),
            prompt=prompt_template,
        )

        # Combine retrieved docs into the {context} variable of the LLM chain
        combine_docs_chain = StuffDocumentsChain(
            llm_chain=llm_chain,
            document_variable_name="context",
        )

        # Optional: question reformulation. We reuse same prompt/LLM for simplicity.
        question_generator = LLMChain(
            llm=ChatOpenAI(model_name=model_name, temperature=temperature),
            prompt=prompt_template,
        )

        # Final QA chain with conversation memory
        self.chain = ConversationalRetrievalChain(
            retriever=self.retriever,
            combine_docs_chain=combine_docs_chain,
            memory=ConversationBufferMemory(
                memory_key="chat_history", return_messages=True
            ),
            question_generator=question_generator,
        )

    # ---------- Internal helper ----------

    def _has_relevant_context(self, question: str) -> bool:
        """
        Checks for relevant context using the vector store.
        Mirrors your previous controller-side logic:
        - Prefer `similarity_search_with_score(k=1)` when available.
        - Fallback to `get_relevant_documents`.
        """
        try:
            vs = getattr(self.retriever, "vectorstore", None)
            if vs and hasattr(vs, "similarity_search_with_score"):
                pairs = vs.similarity_search_with_score(query=question, k=1)
                return bool(pairs)  # same as before: any hit -> consider relevant

            # Fallback without scores
            docs = self.retriever.get_relevant_documents(question)
            return bool(
                docs and any((getattr(d, "page_content", "") or "").strip() for d in docs)
            )

        except Exception as ex:
            self.logger.error("context_check_error", extra={"error": str(ex)})
            return False

    # ---------- Public API ----------

    def answer(self, question: str) -> str:
        """
        Backward-compatible alias to `handle()`.
        """
        return self.handle(question)

    def handle(self, user_query: str) -> str:
        """
        Route the query:
          - If no relevant documents are found, use the prompt-only fallback.
          - Otherwise, use the QA chain with retrieved context.
        NOTE: Keeps `.run(...)` to avoid changing runtime behavior.
        """
        # Quick retrieval (no scores) to keep existing behavior for logging granularity
        docs = self.retriever.get_relevant_documents(user_query)

        if not docs or all((getattr(doc, "page_content", "") or "").strip() == "" for doc in docs):
            self.logger.info("No relevant documents from FAISS. Using prompt fallback.")
            self.logger.debug(f"Query: {user_query}")
            return self.prompt_bot.handle(user_query)

        # Extra guard: if vector store says there are hits, log RAG path explicitly
        if not self._has_relevant_context(user_query):
            # Should rarely happen, but keeps behavior conservative
            self.logger.info("Context check failed. Using prompt fallback.")
            self.logger.debug(f"Query: {user_query}")
            return self.prompt_bot.handle(user_query)

        self.logger.info("Relevant context found in FAISS. Using QA chain.")
        self.logger.debug(f"Query: {user_query} | Context docs: {len(docs)}")
        return self.chain.run(user_query)
