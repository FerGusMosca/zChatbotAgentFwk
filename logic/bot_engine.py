import os
from dotenv import load_dotenv
from langchain.chains import ConversationalRetrievalChain
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.memory import ConversationBufferMemory

from logic.pipeline.hybrid_bot import HybridBot
from logic.pipeline.prompt_based_chatbot import PromptBasedChatbot
from logic.prompt_loader import PromptLoader

load_dotenv()


def load_bot_for_client(client_name: str):
    """
    Loads a chatbot that uses only prompt-based behavior.

    This bot:
    - Does NOT use FAISS or any vector database.
    - Does NOT answer content-specific questions.
    - Only responds using predefined prompts (e.g., tone, role, structure).

    Use case:
    - Useful for stylistic assistants or copilots that don't need knowledge retrieval.
    """
    prompt_name = os.getenv("ZBOT_PROMPT_NAME", "generic_prompt")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    loader = PromptLoader(os.path.join(base_dir, "../prompts"))
    return PromptBasedChatbot(loader, prompt_name=prompt_name)


def load_qa_chain_for_client(client_id="demo_client"):
    """
    Loads a simple QA bot using only FAISS and memory (RAG-style).

    This bot:
    - Uses a trained FAISS vector store to retrieve knowledge.
    - Uses LangChain memory to retain conversational context.
    - Does NOT use prompts for style.
    - Does NOT fallback to general OpenAI completion when no match is found.

    Use case:
    - Good for pure knowledge-retrieval chatbots without behavioral customization.
    """
    print(f"🤖 Loading QA bot for client: {client_id}")

    vectorstore_path = f"vectorstores/{client_id}"
    vectordb = FAISS.load_local(
        vectorstore_path,
        OpenAIEmbeddings(),
        allow_dangerous_deserialization=True
    )

    llm = ChatOpenAI(temperature=0)
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

    qa_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=vectordb.as_retriever(),
        memory=memory
    )

    return qa_chain


def load_hybrid_bot(client_id="demo_client"):
    """
    Loads the full hybrid bot: FAISS + prompt-based behavior + OpenAI fallback.

    This bot:
    - Uses FAISS to retrieve trained content.
    - Uses a prompt to define behavior and tone.
    - Falls back to OpenAI (general knowledge) if no relevant document is found.

    Use case:
    - Ideal for production-grade assistants combining structure, knowledge and flexibility.
    """
    print(f"🤖 Loading hybrid bot for client: {client_id}")

    vectorstore_path = f"vectorstores/{client_id}"
    vectordb = FAISS.load_local(
        vectorstore_path,
        OpenAIEmbeddings(),
        allow_dangerous_deserialization=True
    )

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    prompts_path = os.path.join(base_dir, "prompts")
    prompt_loader = PromptLoader(prompts_path,prompt_name=os.getenv("ZBOT_PROMPT_NAME", "generic_prompt"))
    prompt_bot = PromptBasedChatbot(
        prompt_loader,
        prompt_name=os.getenv("ZBOT_PROMPT_NAME", "generic_prompt")
    )

    return HybridBot(vectordb, prompt_bot)
