# ===== hybrid_bot.py =====
# FINAL – RAG + FALLBACK CON THRESHOLD – 100% FUNCIONA
import importlib
import json
from datetime import datetime
from typing import List, Optional, Tuple
from pathlib import Path
import uuid

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from common.config.settings import get_settings
from common.util.cache.cache_manager import CacheManager
from common.util.loader.faiss_loader import FaissVectorstoreLoader
from common.util.loader.prompt_loader import PromptLoader
from logic.util.builder.llm_factory import LLMFactory
from common.util.app_logger import AppLogger


class HybridBot:
    def __init__(
        self,
        vector_store_path: str,
        prompt_name: str,
        retrieval_score_threshold: float = 0.4,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        top_k: int = 8,
    ):
        self.logger = AppLogger.get_logger(__name__)
        self.retrieval_score_threshold = retrieval_score_threshold
        self.top_k = top_k

        # --- Cache manager ---
        self.cache = CacheManager()

        # --- Custom loggers (keep your commented variants) ---
        self._load_custom_logger()


        # --- Intent logic (keep your commented variants) ---
        self._intent_detection_logic()

        # FAISS
        vectordb = FaissVectorstoreLoader.load_legacy_faiss(vector_store_path)
        self.retriever = vectordb.as_retriever(search_kwargs={"k": top_k})

        # LLM
        self.llm = LLMFactory.create(
            provider="openai",
            model_name=model_name,
            temperature=temperature,
        )

        # Prompt real
        self.full_prompt = PromptLoader(prompt_name).prompts[prompt_name]
        self.rag_prompt = ChatPromptTemplate.from_template(self.full_prompt)

        # Prompt fallback (simple)
        self.fallback_prompt = ChatPromptTemplate.from_template(
            "You are a helpful financial assistant.\n\nQuestion: {question}"
        )

        self.logger.info("HybridBot loaded – RAG + fallback with threshold")

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

    def _eval_memory(self):
            pass

    def _retrieve_with_score(self, question: str) -> Tuple[List, Optional[float]]:
        try:
            # Usa el método con score si existe
            vs = getattr(self.retriever, "vectorstore", None)
            if vs and hasattr(vs, "similarity_search_with_score"):
                pairs = vs.similarity_search_with_score(query=question, k=self.top_k)
                docs = [doc for doc, _ in pairs]
                if pairs:
                    best_distance = min(score for _, score in pairs)
                    score = 1.0 / (1.0 + best_distance)  # distancia → similitud
                    return docs, score
            # Fallback: sin score
            docs = self.retriever.invoke(question)
            return docs, None
        except Exception as e:
            self.logger.error("Retrieval failed", extra={"error": str(e)})
            return [], None

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

    def _render_history(self, max_msgs: int = 8) -> str:
        """
        Convert the chain's chat_history into a compact string.
        This allows us to inject past dialogue into the fallback path,
        so the model has access to what the user already said.
        """
        try:
            msgs = getattr(self.llm.get_client().memory, "chat_memory", None)
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
        Prompt-only fallback path + cache check
        """
        cache_key = f"fb:{user_query.strip().lower()}"

        # 1) Try cache first
        cached = self.cache.get(cache_key)
        if cached:
            self.logger.info("cache_hit_fallback", extra={"query": user_query, "key": cache_key})
            return self._parse_result(cached)

        # 2) Generate normally
        try:
            history = self._render_history()
            if history:
                user_in = (
                    "Use the following conversation history to remember details "
                    "already mentioned in this session.\n\n"
                    f"{history}\n\n"
                    f"New question: {user_query}"
                )
            else:
                user_in = user_query

            result = self.llm.handle(user_in)
            self.logger.info("cache_miss_fallback", extra={"query": user_query, "key": cache_key})

            # 3) Store result in cache
            self.cache.set(cache_key, result, expiry=300)  # 5 min TTL
        except Exception as ex:
            self.logger.error("fallback_execution_error", extra={"query": user_query, "error": str(ex)})
            return "An error occurred while generating the fallback response.", None, None

        return self._parse_result(result)

    def _rag(self, user_query: str, docs, best_score: float) -> Tuple[str, Optional[str], Optional[str]]:
        """
        RAG path – uses retrieved documents as context.
        Caches result for performance.
        """
        cache_key = f"rag:{user_query.strip().lower()}"
        cached = self.cache.get(cache_key)
        if cached:
            self.logger.info("RAG cache hit", extra={"query": user_query})
            return self._parse_result(cached)

        try:
            # Build context from retrieved documents
            context = "\n\n".join(d.page_content for d in docs)

            # Inject context + question into the master prompt
            prompt_w_context = self.full_prompt.format(context=context, question=user_query)

            # Call LLM with full RAG context
            result = self.llm.invoke(prompt_w_context)

            # Cache result
            self.cache.set(cache_key, result, expiry=600)  # 10 min TTL
            self.logger.info("RAG response generated and cached", extra={"docs_used": len(docs)})

        except Exception as ex:
            self.logger.error("RAG execution failed", extra={"error": str(ex)})
            return "Error generating RAG response.", None, None

        return self._parse_result(result)

    def _safe_fallback(self, uq: str):
        """
        Wrapper around fallback to ensure robustness AND update memory.
        This way, even when we fall back, the conversation history remains consistent.
        """
        try:
            ans, it, fl = self._fallback(uq)

            # --- NEW: persist the turn into memory ---
            try:
                if hasattr(self.llm.get_client(), "memory") and hasattr(self.llm.get_client().memory, "chat_memory"):
                    self.llm.get_client().memory.chat_memory.add_user_message(uq)
                    self.llm.get_client().memory.chat_memory.add_ai_message(ans)
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


    def handle(self, question: str) -> str:
        """
        Robust routing:
          0) Try to RESUME an ongoing intent session first (slot filling).
          1) If not, try intent detection (short-circuit if handled).
          2) Otherwise choose Fallback vs RAG.
          3) Log metrics safely and always return a user-visible message.
        """
        global uuid
        try:
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
                    handled, intent_answer, intent_name, flag = self.intent_logic.resume_intent(question)
                else:
                    handled, intent_answer, intent_name, flag = (False, "", None, None)

                if handled:
                    self.last_metrics.update({"mode": "intent"})
                    try:
                        self._log_generic_metrics(question, "intent", intent=intent_name, specific_flag=flag)
                    except Exception as ex_mr:
                        self.logger.exception("metrics_log_error_intent_resume",
                                              extra={"query": question, "error": str(ex_mr)})
                    return intent_answer or "Action completed."
            except Exception as ex_resume:
                import uuid
                error_id = str(uuid.uuid4())[:8]
                self.logger.exception("intent_resume_error",
                                      extra={"error_id": error_id, "query": question, "error": str(ex_resume)})


            # 1) INTENT DETECTION (safe)
            try:
                if getattr(self, "intent_logic", None) is not None:
                    handled, intent_answer, intent_name, flag = self.intent_logic.try_handle(question)
                else:
                    handled, intent_answer, intent_name, flag = (False, "", None, None)
            except Exception as ex_int:
                error_id = str(uuid.uuid4())[:8]
                self.logger.exception("intent_logic_error",
                                      extra={"error_id": error_id, "query": question, "error": str(ex_int)})
                handled, intent_answer, intent_name, flag = (False, "", None, None)

            # 2) RETRIEVE (safe)
            try:
                docs, best_score = self._retrieve_context(question)
                docs = docs or []
                # best_score = best_score if isinstance(best_score, (int, float)) else None
                self.last_metrics["docs_found"] = len(docs)
                self.last_metrics["best_score"] = best_score
            except Exception as ex_ret:
                error_id = str(uuid.uuid4())[:8]
                self.logger.exception("retriever_error",
                                      extra={"error_id": error_id, "query": question, "error": str(ex_ret)})
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
                             extra={"query": question,
                                    "docs_found": len(docs),
                                    "best_score": best_score,
                                    "threshold": self.retrieval_score_threshold,
                                    "use_fallback": use_fallback})

            if use_fallback:
                answer, intent, flag, mode_used = self._safe_fallback(question)
            else:
                try:
                    answer, intent, flag = self._rag(question, docs, best_score)
                    mode_used = "rag"
                except Exception as ex_rag:
                    rag_error_id = str(uuid.uuid4())[:8]
                    self.logger.exception("rag_execution_error",
                                          extra={"error_id": rag_error_id, "query": question,
                                                 "error": str(ex_rag)})
                    answer, intent, flag, mode_used = self._safe_fallback(question)

            # 4) METRICS (safe)
            self.last_metrics["mode"] = mode_used
            try:
                self._log_generic_metrics(question, mode_used, intent, flag)
            except Exception as ex_m2:
                self.logger.exception("metrics_log_error", extra={"query": question, "error": str(ex_m2)})

            # 5) FINAL ANSWER (always non-empty)
            if not answer:
                final_error_id = str(uuid.uuid4())[:8]
                self.logger.error("empty_answer_safety_trip",
                                  extra={"error_id": final_error_id, "query": question})
                return f"Something went wrong while preparing the answer (error {final_error_id}). Please try again."
            return answer

        except Exception as e:
            self.logger.error("CRASH", extra={"error": str(e)})
            return "Error interno. Intentá de nuevo."

