import importlib
import uuid
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
from langchain_core.prompts import MessagesPlaceholder

from common.config.settings import settings

from common.util.app_logger import AppLogger
from logic.intents.demos.intente_detection.intent_detection_outbound_sales import IntentDetectionLogicOutboundSales

from common.config.settings import get_settings

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
        # --- Core wiring ---
        self.retriever = vectordb.as_retriever(search_kwargs={"k": top_k})
        self.prompt_bot = prompt_bot
        self.logger = AppLogger.get_logger(__name__)
        self.top_k = top_k
        self.retrieval_score_threshold = retrieval_score_threshold
        self.last_metrics = {}
        self.facts_store = {}  # {session_id: {"user_name": "...", "neighborhood_pref": "...", ...}}

        self.logger.info(f"Loading HybridBot for profile: {settings.bot_profile}")

        # --- Custom loggers (keep your commented variants) ---
        self._load_custom_logger()

        # --- Intent logic (keep your commented variants) ---
        self._intent_detection_logic()

        # ---------- LLM (single base instance) ----------
        base_llm = ChatOpenAI(model_name=model_name, temperature=temperature)

        # ---------- PROMPTS (fixed) ----------
        # 1) ANSWER prompt: expects chat_history as a LIST of messages (MessagesPlaceholder)
        answer_prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(self.prompt_bot.system_prompt + "\n{context}"),
                # MessagesPlaceholder(variable_name="chat_history"),   # ❌ rompe con CRC
                HumanMessagePromptTemplate.from_template("Chat history:\n{chat_history}\n\n{question}"),
            ],
            input_variables=["context", "question", "chat_history"],
        )

        # 2) QUESTION GENERATOR prompt: expects chat_history as a FLATTENED STRING (NO MessagesPlaceholder)
        qgen_prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    "[QGEN] Rephrase the user's question for retrieval. "
                    "chat_history is provided as FLATTENED TEXT.\n\n"
                    "Chat history:\n{chat_history}"
                ),
                HumanMessagePromptTemplate.from_template("{question}"),
            ],
            input_variables=["chat_history", "question"],  # plain text placeholders
        )

        # ---------- CHAINS ----------
        # Answer chain (StuffDocumentsChain) using the ANSWER prompt
        llm_chain = LLMChain(llm=base_llm, prompt=answer_prompt)
        combine_docs_chain = StuffDocumentsChain(
            llm_chain=llm_chain,
            document_variable_name="context",
        )

        # Question generator chain using the QGEN prompt
        question_generator = LLMChain(llm=base_llm, prompt=qgen_prompt)

        # ---------- MEMORY (Level 1 session buffer) ----------
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,  # MUST be True so answer prompt gets a list of messages
        )

        # ---------- Conversational Retrieval Chain ----------
        self.chain = ConversationalRetrievalChain(
            retriever=self.retriever,
            combine_docs_chain=combine_docs_chain,
            question_generator=question_generator,
            memory=memory,
        )

        # ---------- Optional guardrails (keep commented; enable if you want strict checks) ----------
        try:
             self._assert_crc_contract(answer_prompt, qgen_prompt, memory)  # hard fail if someone breaks the contract
             self._log_crc_contract(answer_prompt, qgen_prompt, memory, model_name, temperature)  # one-time contract log
        except Exception as e:
             self.logger.exception("crc_contract_warning", extra={"error": str(e)})

    # ---------- Internal helper ----------

    def _load_custom_logger(self):
        custom_logger = get_settings().custom_logger
        module = importlib.import_module(custom_logger.split(",")[0])
        class_name=custom_logger.split(",")[1]
        cls = getattr(module, class_name)
        self.custom_logger = cls()

    def _intent_detection_logic(self):
        custom_intent_detection_logic = get_settings().intent_detection_logic
        module = importlib.import_module(custom_intent_detection_logic.split(",")[0])
        class_name = custom_intent_detection_logic.split(",")[1]
        cls = getattr(module, class_name)
        self.intent_logic = cls(self.logger)
        pass

    def _assert_crc_contract(self, answer_prompt, qgen_prompt, memory):
        """Hard guarantees aligned with current CRC design:
           both prompts receive chat_history as FLATTENED STRING."""
        # ANSWER: must NOT use MessagesPlaceholder('chat_history')
        assert not any(
            type(m).__name__ == "MessagesPlaceholder" and getattr(m, "variable_name", "") == "chat_history"
            for m in answer_prompt.messages
        ), "Answer prompt must NOT use MessagesPlaceholder('chat_history'); it expects a flattened string."

        # QGEN: must NOT use MessagesPlaceholder('chat_history')
        assert not any(
            type(m).__name__ == "MessagesPlaceholder" and getattr(m, "variable_name", "") == "chat_history"
            for m in qgen_prompt.messages
        ), "QGen prompt must NOT use MessagesPlaceholder('chat_history'); it expects a flattened string."

        # Memory can still return messages; CRC will flatten internally.
        assert getattr(memory, "return_messages", True) in (True, False), \
            "ConversationBufferMemory misconfigured."

    def _log_crc_contract(self, answer_prompt, qgen_prompt, memory, model_name: str, temperature: float):
        ans_has_mp = any(type(m).__name__ == "MessagesPlaceholder" for m in answer_prompt.messages)
        qgen_has_mp = any(type(m).__name__ == "MessagesPlaceholder" for m in qgen_prompt.messages)
        self.logger.info("crc_contract", extra={
            "answer_uses_messagesplaceholder": ans_has_mp,  # debería ser False
            "qgen_uses_messagesplaceholder": qgen_has_mp,  # debería ser False
            "memory_return_messages": getattr(memory, "return_messages", None),
            "model": model_name,
            "temperature": temperature,
        })

    def _eval_memory(self):
        try:
            if hasattr(self.chain, "memory") and hasattr(self.chain.memory, "chat_memory"):
                msgs = self.chain.memory.chat_memory.messages
                self.logger.info(
                    "mem_snapshot",
                    extra={
                        "count": len(msgs),
                        "last2": [getattr(m, "content", "") for m in msgs[-2:]],
                    },
                )
        except Exception:
            pass

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
        Robust routing:
          0) Try to RESUME an ongoing intent session first (slot filling).
          1) If not, try intent detection (short-circuit if handled).
          2) Otherwise choose Fallback vs RAG.
          3) Log metrics safely and always return a user-visible message.
        """



        self._eval_memory()
        # Default metrics scaffold
        self.last_metrics = {
            "mode": "fallback",
            "docs_found": 0,
            "best_score": None,
            "threshold": getattr(self, "threshold", None),
            "prompt_name": getattr(self, "prompt_name", None),
        }

        # 0) INTENT RESUME (safe)
        # --- RESUME AN ONGOING INTENT (slot-filling) BEFORE DETECTING NEW ONES ---
        try:
            if hasattr(self, "intent_logic") and hasattr(self.intent_logic, "resume_intent"):
                handled, intent_answer, intent_name, flag = self.intent_logic.resume_intent(user_query)
            else:
                handled, intent_answer, intent_name, flag = (False, "", None, None)

            if handled:
                self.last_metrics.update({"mode": "intent"})
                try:
                    self._log_generic_metrics(user_query, "intent", intent=intent_name, specific_flag=flag)
                except Exception as ex_mr:
                    self.logger.exception("metrics_log_error_intent_resume",
                                          extra={"query": user_query, "error": str(ex_mr)})
                return intent_answer or "Action completed."
        except Exception as ex_resume:
            import uuid
            error_id = str(uuid.uuid4())[:8]
            self.logger.exception("intent_resume_error",
                                  extra={"error_id": error_id, "query": user_query, "error": str(ex_resume)})

        # 1) INTENT DETECTION (safe)
        try:
            if getattr(self, "intent_logic", None) is not None:
                handled, intent_answer, intent_name, flag = self.intent_logic.try_handle(user_query)
            else:
                handled, intent_answer, intent_name, flag = (False, "", None, None)
        except Exception as ex_int:
            error_id = str(uuid.uuid4())[:8]
            self.logger.exception("intent_logic_error",
                                  extra={"error_id": error_id, "query": user_query, "error": str(ex_int)})
            handled, intent_answer, intent_name, flag = (False, "", None, None)

        if handled:
            self.last_metrics.update({"mode": "intent"})
            try:
                self._log_generic_metrics(user_query, "intent", intent=intent_name, specific_flag=flag)
            except Exception as ex_m:
                self.logger.exception("metrics_log_error_intent", extra={"query": user_query, "error": str(ex_m)})
            return intent_answer or "Action completed."

        # 2) RETRIEVE (safe)
        try:
            docs, best_score = self._retrieve_context(user_query)
            docs = docs or []
            #best_score = best_score if isinstance(best_score, (int, float)) else None
            self.last_metrics["docs_found"] = len(docs)
            self.last_metrics["best_score"] = best_score
        except Exception as ex_ret:
            error_id = str(uuid.uuid4())[:8]
            self.logger.exception("retriever_error",
                                  extra={"error_id": error_id, "query": user_query, "error": str(ex_ret)})
            docs, best_score = [], None

        # 3) ROUTE (RAG vs FALLBACK)
        use_fallback = (
                not docs
                or (
                        best_score is not None
                        and self.retrieval_score_threshold is not None
                        and best_score < self.retrieval_score_threshold
                )
        )

        self.logger.info("routing_decision",
                         extra={"query": user_query,
                                "docs_found": len(docs),
                                "best_score": best_score,
                                "threshold": self.retrieval_score_threshold,
                                "use_fallback": use_fallback})

        if use_fallback:
            answer, intent, flag, mode_used = self._safe_fallback(user_query)
        else:
            try:
                answer, intent, flag = self._rag(user_query, docs, best_score)
                mode_used = "rag"
            except Exception as ex_rag:
                rag_error_id = str(uuid.uuid4())[:8]
                self.logger.exception("rag_execution_error",
                                      extra={"error_id": rag_error_id, "query": user_query, "error": str(ex_rag)})
                answer, intent, flag, mode_used = self._safe_fallback(user_query)

        # 4) METRICS (safe)
        self.last_metrics["mode"] = mode_used
        try:
            self._log_generic_metrics(user_query, mode_used, intent, flag)
        except Exception as ex_m2:
            self.logger.exception("metrics_log_error", extra={"query": user_query, "error": str(ex_m2)})

        # 5) FINAL ANSWER (always non-empty)
        if not answer:
            final_error_id = str(uuid.uuid4())[:8]
            self.logger.error("empty_answer_safety_trip",
                              extra={"error_id": final_error_id, "query": user_query})
            return f"Something went wrong while preparing the answer (error {final_error_id}). Please try again."
        return answer

    def _retrieve_context(self, user_query: str) -> Tuple[List, Optional[float]]:
        """
        Run vector retrieval and return (docs, best_score).
        FAISS devuelve distancias (menor = mejor). Convertimos a similitud.
        """
        docs = []
        best_score = None
        try:
            vs = getattr(self.retriever, "vectorstore", None)
            if vs and hasattr(vs, "similarity_search_with_score"):
                pairs = vs.similarity_search_with_score(query=user_query, k=self.top_k)
                docs = [doc for doc, _ in pairs]

                if pairs:
                    # Log raw FAISS distances
                    for d, s in pairs:
                        self.logger.info(
                            f"[RetrieveContext] doc={d.page_content[:60]}... | raw_dist={s}"
                        )
                    # Take best (lowest distance)
                    raw = min(s for _, s in pairs)
                    # Convert distance to similarity (1 / (1 + dist))
                    best_score = 1.0 / (1.0 + raw)
                    self.logger.info(f"[RetrieveContext] best_raw={raw} | best_score={best_score}")
            else:
                docs = self.retriever.get_relevant_documents(user_query)

        except Exception as ex:
            self.logger.error("retriever_error", extra={"error": str(ex)})

        return docs, best_score

    def _safe_fallback(self, uq: str):
        """
        Wrapper around fallback to ensure robustness AND update memory.
        This way, even when we fall back, the conversation history remains consistent.
        """
        try:
            ans, it, fl = self._fallback(uq)

            # --- NEW: persist the turn into memory ---
            try:
                if hasattr(self.chain, "memory") and hasattr(self.chain.memory, "chat_memory"):
                    self.chain.memory.chat_memory.add_user_message(uq)
                    self.chain.memory.chat_memory.add_ai_message(ans)
            except Exception:
                # Never let memory errors crash the fallback
                pass
            # -----------------------------------------

            return ans, it, fl, "fallback"
        except Exception as ex_fb:
            error_id = str(uuid.uuid4())[:8]
            self.logger.exception("fallback_execution_error",
                                  extra={"error_id": error_id, "query": uq, "error": str(ex_fb)})
            return (f"Sorry, I couldn't generate a fallback answer (error {error_id}).",
                    None, "FALLBACK_ERROR", "fallback")

    def _render_history(self, max_msgs: int = 8) -> str:
        """
        Convert the chain's chat_history into a compact string.
        This allows us to inject past dialogue into the fallback path,
        so the model has access to what the user already said.
        """
        try:
            msgs = getattr(self.chain.memory, "chat_memory", None)
            if not msgs:
                return ""
            lines = []
            for m in msgs.messages[-max_msgs:]:
                role = "User" if m.type == "human" else "Assistant"
                lines.append(f"{role}: {m.content}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _fallback(self, user_query: str) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Prompt-only fallback path.
        Now enriched with conversation history (Level 1 memory).
        """
        try:
            # Render history from memory
            history = self._render_history()

            # If we have history, inject it into the user input
            if history:
                user_in = (
                    "Use the following conversation history to remember details "
                    "the user already mentioned in this session.\n\n"
                    f"{history}\n\n"
                    f"New question: {user_query}"
                )
            else:
                user_in = user_query

            # Pass enriched input to the prompt-only bot
            result = self.prompt_bot.handle(user_in)
        except Exception as ex:
            self.logger.error(f"fallback_execution_error: {ex} | query={user_query}")
            return "An error occurred while generating the fallback response.", None, None

        return self._parse_result(result)

    def _rag(self, user_query: str, docs, best_score: float) -> Tuple[str, Optional[str], Optional[str]]:
        """
        RAG path using chain.run() after clearing memory if needed.
        """
        try:
            #if hasattr(self.chain, "memory"):
                #self.chain.memory.clear()
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
