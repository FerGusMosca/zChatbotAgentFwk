from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.chains.llm import LLMChain
from langchain.chains.combine_documents.stuff import StuffDocumentsChain
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_community.chat_models import ChatOpenAI


class HybridBot:
    def __init__(self, vectordb, prompt_bot):
        self.retriever = vectordb.as_retriever()
        self.prompt_bot = prompt_bot

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
            llm=ChatOpenAI(model_name="gpt-4o", emperature=0),
            prompt=prompt_template,  # o usá otro más simple si solo querés reformulación
        )

        # 🧠 QA Chain final con memoria de conversación
        self.chain = ConversationalRetrievalChain(
            retriever=self.retriever,
            combine_docs_chain=combine_docs_chain,
            memory=ConversationBufferMemory(memory_key="chat_history", return_messages=True),
            question_generator=question_generator
        )

    def handle(self, user_query: str) -> str:
        docs = self.retriever.get_relevant_documents(user_query)
        if not docs or all(doc.page_content.strip() == "" for doc in docs):
            print("[DEBUG] No relevant documents from FAISS. Using prompt fallback.")
            return self.prompt_bot.handle(user_query)
        else:
            print("[DEBUG] Relevant context found in FAISS. Using QA chain.")
            return self.chain.run(user_query)
