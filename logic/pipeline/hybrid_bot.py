# logic/pipeline/hybrid_bot.py
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.chains.llm import LLMChain
from langchain.chains.combine_documents.stuff import StuffDocumentsChain
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_community.chat_models import ChatOpenAI

from common.util.app_logger import AppLogger


class HybridBot:
    """
    Orchestrates a hybrid flow:
      1) Try RAG (retrieval + LLM) when relevant context exists.
      2) Fallback to prompt-only bot when no relevant docs are found.

    Notes:
    - Keeps a conversation memory so reformulated questions work.
    - Uses the SAME system prompt for both RAG and fallback so tone is consistent.
    """

    def __init__(self, vectordb, prompt_bot, model_name: str = "gpt-4o", top_k: int = 4):
        self.retriever = vectordb.as_retriever(search_kwargs={"k": top_k})
        self.prompt_bot = prompt_bot
        self.logger = AppLogger.get_logger(__name__)

        # Build a composable prompt: system + context + user question.
        prompt_template = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    # We append {context} to system so the LLM treats it as authoritative input.
                    prompt_bot.system_prompt + "\n\n{context}"
                ),
                HumanMessagePromptTemplate.from_template("{question}")
            ],
            input_variables=["context", "question"]
        )

        # LLM chain using the full prompt (system + context + question).
        llm_chain = LLMChain(
            llm=ChatOpenAI(model_name=model_name, temperature=0),
            prompt=prompt_template
        )

        # Combine retrieved docs into the {context} variable for the LLM chain.
        combine_docs_chain = StuffDocumentsChain(
            llm_chain=llm_chain,
            document_variable_name="context"
        )

        # Optional: question reformulation (kept simple — reuse same prompt).
        question_generator = LLMChain(
            llm=ChatOpenAI(model_name=model_name, temperature=0),
            prompt=prompt_template,
        )

        # Final QA chain with conversation memory.
        self.chain = ConversationalRetrievalChain(
            retriever=self.retriever,
            combine_docs_chain=combine_docs_chain,
            memory=ConversationBufferMemory(memory_key="chat_history", return_messages=True),
            question_generator=question_generator
        )

    def handle(self, user_query: str) -> str:
        """
        Route the query:
          - If retriever yields no meaningful docs, use fallback (prompt-only).
          - Otherwise, run the QA chain with context.
        """
        docs = self.retriever.get_relevant_documents(user_query)
        has_context = bool(docs and any((d.page_content or "").strip() for d in docs))

        if not has_context:
            self.logger.info(
                "hybrid_decision",
                extra={"mode": "fallback", "docs_found": 0, "query": user_query[:200]}
            )
            return self.prompt_bot.handle(user_query)

        self.logger.info(
            "hybrid_decision",
            extra={"mode": "rag", "docs_found": len(docs), "query": user_query[:200]}
        )
        return self.chain.run(user_query)
