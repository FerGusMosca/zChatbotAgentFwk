# ===== rag_only_bot.py =====
# All comments MUST be in English.

import os
import pickle
import uuid
import json
from datetime import datetime

import faiss
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.chains import (
    create_history_aware_retriever,
    create_retrieval_chain,
)

from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate,
)

from langchain_core.runnables import RunnableWithMessageHistory, RunnablePassthrough
from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

from common.config.settings import get_settings
from common.util.loader.faiss_loader import FaissVectorstoreLoader


class RagOnlyBot:
    """Pure Retrieval-Augmented Generation bot (A2 memory FIXED)."""

    def __init__(
            self,
            vector_store_path,
            prompt_name,
            system_prompt: str = "",
            llm_prov:str="openai",
            model_name: str = "gpt-4o",
            temperature: float = 0.0,
            top_k: int = 4,
            retrieval_score_threshold: float = None,
            logger=None,
    ):
        # Logging
        self.logger = logger
        self.prompt_bot = None #NO FALLBACK!
        self.prompt_name=prompt_name
        self.system_prompt = system_prompt
        self.top_k = top_k
        self.retrieval_score_threshold = retrieval_score_threshold

        # In-memory histories
        self.chat_store = {}

        # === Load FAISS vectorstore (single source of truth) ===
        vectordb, meta =FaissVectorstoreLoader.load_advanced_faiss(vector_store_path)

        self.vectordb = vectordb

        # Build retriever
        self.retriever = self.vectordb.as_retriever(
            search_kwargs={"k": self.top_k}
        )

        # === Base LLM ===
        llm = ChatOpenAI(model_name=model_name, temperature=temperature)

        # === Prompts ===
        contextualize_q = PromptTemplate.from_template(
            "Given the chat history:\n{chat_history}\nRewrite the user question:\n{input}"
        )

        answer_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                self.system_prompt + "\n\nContext:\n{context}"
            ),
            HumanMessagePromptTemplate.from_template(
                "Chat history:\n{chat_history}\n\nQuestion:\n{question}"
            ),
        ])

        # === Retrieval chain ===
        history_aware = create_history_aware_retriever(
            llm=llm,
            retriever=self.retriever,
            prompt=contextualize_q,
        )

        qa_chain = answer_prompt | llm

        retrieval_chain = (
                RunnablePassthrough.assign(context=history_aware)
                | {
                    "context": lambda x: x["context"],
                    "question": lambda x: x["input"],  # Critical fix: input → question
                    "chat_history": lambda x: x.get("chat_history", [])
                }
                | qa_chain
        )

        # === Memory callbacks ===
        def _get_session_history(session_id: str):
            """Return chat history object."""
            return self.chat_store.setdefault(session_id, InMemoryChatMessageHistory())

        def _save_session_history(session_id: str, inputs, outputs):
            """Append Q/A to session history."""
            hist = self.chat_store.setdefault(session_id, InMemoryChatMessageHistory())
            q = inputs.get("input", "")

            # FIX: outputs is now AIMessage, not dict with "answer"
            a = outputs.content if hasattr(outputs, "content") else str(outputs)

            hist.add_user_message(q)
            hist.add_ai_message(a)

            self._log("rag_memory_update", {
                "session_id": session_id,
                "user_msg": q[:100] + "..." if len(q) > 100 else q,
                "ai_msg": a[:100] + "..." if len(a) > 100 else a,
                "history_len": len(hist.messages),
            })

        # === Wrap chain ===
        self.chain = RunnableWithMessageHistory(
            retrieval_chain,
            _get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer",
            store_history=_save_session_history,
        )

    # ===========================
    # VECTORSTORE LOADER
    # ===========================
    def load_vectorstore(self):
        """Load FAISS HNSWFlat index + rebuild docstore manually."""
        try:
            s = get_settings()
            folder = os.path.join(s.bot_profile_root_path, s.bot_profile)

            # --- Load metadata ---
            meta_path = os.path.join(folder, "index.pkl")
            with open(meta_path, "rb") as f:
                meta = pickle.load(f)

            # --- Load FAISS index ---
            faiss_path = os.path.join(folder, "index.faiss")
            index = faiss.read_index(faiss_path)

            # --- Embeddings ---
            emb = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

            # --- Build docstore ---
            chunks = meta["chunks"]
            docstore = InMemoryDocstore({str(i): chunks[i] for i in range(len(chunks))})

            # --- Mapping ---
            mapping = {i: str(i) for i in range(len(chunks))}

            # --- Debug prints ---
            print("======= DEBUG FAISS LOAD =======")
            print("faiss.ntotal:", index.ntotal)
            print("len(chunks):", len(chunks))
            print("mapping keys:", len(mapping))
            print("first_missing_docstore:",
                  next((i for i in range(index.ntotal)
                        if str(i) not in docstore._dict), None))
            print("================================")

            # --- Wrap FAISS ---
            vectordb = FAISS(
                embedding_function=emb,
                index=index,
                docstore=docstore,
                index_to_docstore_id=mapping,
                normalize_L2=False,
            )

            self._log("rag_vectorstore_loaded", {
                "folder": folder,
                "chunks": len(chunks),
                "index_ntotal": index.ntotal,
            })

            return vectordb, meta

        except Exception as ex:
            import traceback
            tb = traceback.format_exc()
            print("\n\n==== HARD FAISS EXCEPTION ====")
            print(tb)
            print("================================\n\n")
            raise

    # ===========================
    # HANDLE QUERY (DEBUG MODE)
    # ===========================
    def handle(self, user_query: str) -> str:
        session_id = "default"

        self._log("rag_request", {"query": user_query})

        try:
            hist = self.chat_store.get(session_id, InMemoryChatMessageHistory())

            self._log("rag_debug_history", {
                "session_id": session_id,
                "history_len": len(hist.messages),
                "history": str([m.content for m in hist.messages]),
            })

            result = self.chain.invoke(
                {"input": user_query},
                config={"configurable": {"session_id": session_id}, "verbose": True},
            )

            self._log("rag_raw_result", {"raw": str(result)})

            ans = result.content if hasattr(result, "content") else str(result)
            parsed = self._safe_json(ans)
            if isinstance(parsed, dict) and "answer" in parsed:
                return parsed["answer"]
            return parsed

        except Exception as ex:
            import traceback
            tb = traceback.format_exc()
            err_id = str(uuid.uuid4())[:8]

            self._log("rag_chain_exception", {
                "error_id": err_id,
                "exception": str(ex),
                "traceback": tb,
                "query": user_query,
            })

            print("\n====== RAG FULL EXCEPTION ======")
            print(tb)
            print("================================\n")

            return f"RAG processing error ({err_id})."

    # ===========================
    # HELPERS
    # ===========================
    def _safe_json(self, txt):
        try:
            return json.loads(txt)
        except:
            return txt

    def _log(self, event, payload):
        if not self.logger:
            return
        try:
            self.logger.info(
                f"LOG EVENT: {event}",
                extra={"timestamp": datetime.utcnow().isoformat(), **payload},
            )
        except:
            pass
