from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.chains.llm import LLMChain
from langchain.chains.combine_documents.stuff import StuffDocumentsChain
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_community.chat_models import ChatOpenAI

from common.util.app_logger import AppLogger


class HybridBot:
    def __init__(self, vectordb, prompt_bot):
        self.retriever = vectordb.as_retriever()
        self.prompt_bot = prompt_bot
        self.logger = AppLogger.get_logger(__name__)

        # 🧠 Crear el prompt que incluye el system_prompt personalizado
        prompt_template = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(prompt_bot.system_prompt + "\n{context}"),
                HumanMessagePromptTemplate.from_template("{question}")
            ],
            input_variables=["context", "question"]
        )

        # 🧠 Cadena base con el LLM y el prompt completo
        llm_chain = LLMChain(
            llm=ChatOpenAI(model_name="gpt-4o", temperature=0),
            prompt=prompt_template
        )

        # 🧠 Encadenar contexto + respuesta
        combine_docs_chain = StuffDocumentsChain(
            llm_chain=llm_chain,
            document_variable_name="context"
        )

        # Podés usar el mismo LLM y prompt si querés algo simple
        question_generator = LLMChain(
            llm=ChatOpenAI(model_name="gpt-4o", temperature=0),
            prompt=prompt_template,  # o usá otro más simple si solo querés reformulación
        )

        # 🧠 QA Chain final con memoria de conversación
        self.chain = ConversationalRetrievalChain(
            retriever=self.retriever,
            combine_docs_chain=combine_docs_chain,
            memory=ConversationBufferMemory(memory_key="chat_history", return_messages=True),
            question_generator=question_generator
        )

    def has_relevant_context(self, question: str) -> bool:
        """Mirror the controller's check: use vectorstore.similarity_search_with_score(k=1)."""
        try:
            retriever = self.retriever
            vs = getattr(retriever, "vectorstore", None)
            if vs and hasattr(vs, "similarity_search_with_score"):
                pairs = vs.similarity_search_with_score(query=question, k=1)
                return bool(pairs)
            # fallback sin scores
            docs = retriever.get_relevant_documents(question)
            return bool(docs and any((getattr(d, "page_content", "") or "").strip() for d in docs))
        except Exception as ex:
            self.logger.error("context_check_error", extra={"error": str(ex)})
            return False

    def answer(self, question: str) -> str:
        """Decide RAG vs fallback here, keeping current behavior."""
        if self.has_relevant_context(question):
            self.logger.info("hybrid_decision", extra={"mode": "rag"})
            # usamos run() porque así te funciona hoy (evitamos romper nada)
            return self.chain.run(question)
        else:
            self.logger.info("hybrid_decision", extra={"mode": "fallback"})
            return self.prompt_bot.handle(question)

    import logging



    def handle(self, user_query: str) -> str:
        docs = self.retriever.get_relevant_documents(user_query)

        if not docs or all(doc.page_content.strip() == "" for doc in docs):
            self.logger.info("No relevant documents from FAISS. Using prompt fallback.")
            self.logger.debug(f"Query: {user_query}")
            return self.prompt_bot.handle(user_query)
        else:
            self.logger.info("Relevant context found in FAISS. Using QA chain.")
            self.logger.debug(f"Query: {user_query} | Context docs: {len(docs)}")
            return self.chain.run(user_query)

