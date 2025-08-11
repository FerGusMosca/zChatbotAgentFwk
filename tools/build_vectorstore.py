import os
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.schema import Document
import docx2txt

from common.config.settings import get_settings

load_dotenv()


def load_documents_from_folder(folder_path):
    docs = []
    for filename in os.listdir(folder_path):
        full_path = os.path.join(folder_path, filename)

        if filename.endswith(".pdf"):
            loader = PyPDFLoader(full_path)
            docs.extend(loader.load())

        elif filename.endswith(".txt"):
            loader = TextLoader(full_path)
            docs.extend(loader.load())

        elif filename.endswith(".docx"):
            try:
                raw_text = docx2txt.process(full_path)
                if raw_text.strip():  # Si tiene contenido
                    doc = Document(page_content=raw_text, metadata={"source": filename})
                    docs.append(doc)
                else:
                    print(f"⚠️ Empty DOCX file: {filename}")
            except Exception as e:
                print(f"❌ Error loading DOCX file {filename}: {str(e)}")

        else:
            print(f"❌ Unsupported file format: {filename}")

    return docs


def build_vectorstore(client_id):
    doc_path = f"data/documents/{client_id}"
    vectorstore_path = f"vectorstores/{client_id}"

    print(f"📂 Loading documents from: {doc_path}")
    documents = load_documents_from_folder(doc_path)

    if not documents:
        print("⚠️ No documents found.")
        return

    print(f"📄 Loaded {len(documents)} document chunks.")
    embeddings = OpenAIEmbeddings()
    vectordb = FAISS.from_documents(documents, embeddings)

    os.makedirs(vectorstore_path, exist_ok=True)
    vectordb.save_local(vectorstore_path)
    print(f"✅ Vectorstore saved to: {vectorstore_path}")


if __name__ == "__main__":
    client_id = get_settings().bot_profile
    build_vectorstore(client_id)
