from datetime import datetime
from typing import Optional, List, Tuple
import json
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


from common.config.settings import settings

from common.util.app_logger import AppLogger
from logic.logic.custom_logging_logic import CustomLoggingLogic
from logic.logic.custom_logic_august_investments import CustomLoggingLogicAugustInvestments
from logic.logic.dyncamic_topic_extractor import  DynamicTopicExtractorLLM


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
        retrieval_score_threshold=0.4,
        model_name: str = "gpt-4o",
        temperature: float = 0.0,
        top_k: int = 4,
    ):

        self.retriever = vectordb.as_retriever(search_kwargs={"k": top_k})
        self.prompt_bot = prompt_bot
        self.logger = AppLogger.get_logger(__name__)
        self.top_k = top_k
        self.retrieval_score_threshold=retrieval_score_threshold
        self.last_metrics={}

        self.logger.info(f"Loading HybridBot for profile: {settings.bot_profile}")
        #self.custom_logger= CustomLoggingLogicAugustInvestments()#Comment this if turning off the example
        self.custom_logger=CustomLoggingLogic()
        #self.custom_logger=DynamicTopicExtractorLLM()#Comment this if turning off the example


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

    def _log_generic_metrics(self, user_query: str, mode_used: str, intent: str = None, specific_flag: str = None):
        """
        Log generic metrics unless the custom logic handled it.
        """
        # First, let custom logger decide if it wants to handle the event
        if self.custom_logger and self.custom_logger.handle(user_query, self.logger):
            return

        # Otherwise, fallback to generic metrics
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "question": user_query,
            "mode": mode_used,
            "prompt_profile": getattr(self, "prompt_name", None),
        }
        if intent:
            payload["intent"] = intent
        if specific_flag:
            payload["specific_flag"] = specific_flag

        self.logger.info("metric_query_handled", extra=payload)

    def handle(self, user_query: str) -> str:
        """
        Route the query:
          - If no relevant documents are found, use the prompt-only fallback.
          - Otherwise, use the QA chain with retrieved context.
        """
        # Reset default metrics
        self.last_metrics = {
            "mode": "fallback",
            "docs_found": 0,
            "best_score": None,
            "threshold": getattr(self, "threshold", None),
            "prompt_name": getattr(self, "prompt_name", None),
        }

        docs, best_score = self._retrieve_context(user_query)

        # Decide route
        if (
                not docs
                or (
                best_score is not None
                and self.retrieval_score_threshold is not None
                and best_score < self.retrieval_score_threshold
        )
        ):
            answer, intent, flag = self._fallback(user_query)
            mode_used = "fallback"
        else:
            answer, intent, flag = self._rag(user_query, docs, best_score)
            mode_used = "rag"

        # Generic + intent metrics
        self._log_generic_metrics(user_query, mode_used, intent, flag)
        return answer

    def _retrieve_context(self, user_query: str) -> Tuple[List, Optional[float]]:
        """
        Run vector retrieval and return (docs, best_score).
        """
        docs = []
        best_score = None
        try:
            vs = getattr(self.retriever, "vectorstore", None)
            if vs and hasattr(vs, "similarity_search_with_score"):
                pairs = vs.similarity_search_with_score(query=user_query, k=self.top_k)
                docs = [doc for doc, _ in pairs]
                if pairs:
                    raw = float(pairs[0][1])
                    best_score = raw if 0.0 <= raw <= 1.0 else (1.0 / (1.0 + raw))
            else:
                docs = self.retriever.get_relevant_documents(user_query)
        except Exception as ex:
            self.logger.error("retriever_error", extra={"error": str(ex)})
        return docs, best_score

    def _fallback(self, user_query: str) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Prompt-only fallback path.
        """
        try:
            result = self.prompt_bot.handle(user_query)
        except Exception as ex:
            self.logger.error(f"fallback_execution_error: {ex} | query={user_query}")
            return "An error occurred while generating the fallback response.", None, None

        return self._parse_result(result)

    def _rag(self, user_query: str, docs, best_score: float) -> Tuple[str, Optional[str], Optional[str]]:
        """
        RAG path using chain.run() after clearing memory if needed.
        """
        try:
            if hasattr(self.chain, "memory"):
                self.chain.memory.clear()
            result = self.chain.run(user_query)
        except Exception as ex:
            self.logger.error(f"rag_execution_error: {ex} | query={user_query}")
            return "An error occurred while generating the RAG response.", None, None

        return self._parse_result(result)

    def _parse_result(self, result: str) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Extract (answer, intent, specific_flag) from a JSON result; fallback to plain text.
        """
        try:
            parsed = json.loads(result)
            return (
                parsed.get("answer", result),
                parsed.get("intent"),
                parsed.get("specific_flag"),
            )
        except Exception:
            # Log raw result for debugging
            self.logger.error("json_parse_failure", extra={"raw_result": result})
            return result, None, None

    def ask(self, question: str) -> str:
        return self.handle(question)
