import os
from dotenv import load_dotenv
from pathlib import Path
from typing import List
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
import docx2txt

from common.config.settings import get_settings

load_dotenv()

def _clean(text: str) -> str:
    return " ".join(text.replace("\u200b", "").split())

def _split_docs(docs: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900, chunk_overlap=150,
        separators=["\n## ", "\n# ", "\n- ", "\n• ", "\n", " ", ""]
    )
    chunks: List[Document] = []
    for d in docs:
        parts = splitter.split_text(_clean(d.page_content))
        for i, p in enumerate(parts):
            meta = dict(d.metadata)
            meta["chunk"] = i
            chunks.append(Document(page_content=p, metadata=meta))
    return chunks

def load_documents_from_folder(folder_path: str) -> List[Document]:
    docs: List[Document] = []
    for filename in os.listdir(folder_path):
        full_path = os.path.join(folder_path, filename)
        if not os.path.isfile(full_path):
            continue

        if filename.lower().endswith(".pdf"):
            loader = PyPDFLoader(full_path)
            for d in loader.load():
                d.metadata.setdefault("source", filename)
                docs.append(d)

        elif filename.lower().endswith(".txt"):
            loader = TextLoader(full_path, encoding="utf-8")
            for d in loader.load():
                d.metadata.setdefault("source", filename)
                docs.append(d)

        elif filename.lower().endswith(".docx"):
            try:
                raw = docx2txt.process(full_path)
                if raw.strip():
                    docs.append(Document(page_content=raw, metadata={"source": filename}))
                else:
                    print(f"⚠️ Empty DOCX file: {filename}")
            except Exception as e:
                print(f"❌ Error loading DOCX {filename}: {e}")
        else:
            print(f"❌ Unsupported file format: {filename}")
    return docs

def build_vectorstore(client_id: str):
    repo_root = Path(__file__).resolve().parents[1]
    doc_path = repo_root / "data" / "documents" / client_id
    vectorstore_path = repo_root / "vectorstores" / client_id

    print(f"📂 Loading documents from: {doc_path}")
    raw_docs = load_documents_from_folder(str(doc_path))
    if not raw_docs:
        print("⚠️ No documents found.")
        return

    print(f"📄 Loaded {len(raw_docs)} raw docs. Splitting…")
    documents = _split_docs(raw_docs)
    print(f"🧩 Produced {len(documents)} chunks.")

    embeddings = OpenAIEmbeddings()
    vectordb = FAISS.from_documents(documents, embeddings)

    vectorstore_path.mkdir(parents=True, exist_ok=True)
    vectordb.save_local(str(vectorstore_path))
    print(f"✅ Vectorstore saved to: {vectorstore_path}")

if __name__ == "__main__":
    client_id = get_settings().bot_profile
    build_vectorstore(client_id)
