import os
from dotenv import load_dotenv
from langchain.chains import ConversationalRetrievalChain
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.memory import ConversationBufferMemory

load_dotenv()


def load_bot_for_client(client_id="demo_client"):
    print(f"🤖 Loading bot for client: {client_id}")

    # Load FAISS vectorstore for the client
    vectorstore_path = f"vectorstores/{client_id}"
    vectordb = FAISS.load_local(
        vectorstore_path,
        OpenAIEmbeddings(),
        allow_dangerous_deserialization=True
    )

    # Initialize the LLM and conversational memory
    llm = ChatOpenAI(temperature=0)
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

    # Create a conversational retrieval QA chain
    qa_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=vectordb.as_retriever(),
        memory=memory
    )

    return qa_chain
