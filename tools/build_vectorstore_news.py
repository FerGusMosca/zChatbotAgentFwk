import os
import json
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from common.config.settings import get_settings

load_dotenv()


def _clean(text: str) -> str:
    """Remove invisible characters and normalize spaces."""
    return " ".join(text.replace("\u200b", "").split())


def _split_docs(docs: List[Document]) -> List[Document]:
    """Split documents into smaller chunks for embeddings."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=80,
        separators=[". ", "\n", " "]
    )
    chunks = []
    for d in docs:
        parts = splitter.split_text(_clean(d.page_content))
        for i, p in enumerate(parts):
            meta = dict(d.metadata)
            meta["chunk"] = i
            chunks.append(Document(page_content=p, metadata=meta))
    return chunks


def extract_metadata(file_path: str) -> dict:
    """Extract metadata (symbol, date, type) from filename."""
    fname = os.path.basename(file_path)
    parts = fname.split("_")

    meta = {"symbol": None, "date": None, "report_type": "news"}

    if len(parts) >= 2:
        meta["symbol"] = parts[0]
        meta["date"] = parts[1].replace(".json", "")

    return meta


def load_news_documents(folder_path: str) -> list[Document]:
    """Load all .json files from a folder and extract news text."""
    docs = []
    total_files = 0
    processed_files = 0

    for root, _, files in os.walk(folder_path):
        for filename in files:
            total_files += 1
            if not filename.lower().endswith(".json"):
                continue

            full_path = os.path.join(root, filename)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                text = ""
                if isinstance(data, dict):
                    if "headlines" in data and isinstance(data["headlines"], list):
                        headlines = [
                            f"{h.get('title', '').strip()} ({h.get('source','')})"
                            if isinstance(h, dict) else str(h)
                            for h in data["headlines"]
                        ]
                        text = " ".join(headlines)
                    else:
                        text = json.dumps(data)
                else:
                    text = str(data)

                if not text or len(text.strip()) < 50:
                    print(f"⚠️ Skipping {filename}: empty or too short.")
                    continue

                metadata = extract_metadata(full_path)
                metadata["source"] = filename
                docs.append(Document(page_content=text, metadata=metadata))
                processed_files += 1

                print(f"✅ [{processed_files}] Indexed: {filename} | symbol={metadata.get('symbol')}")

            except Exception as e:
                print(f"❌ Error loading {filename}: {e}")

    print(f"📊 Summary: {processed_files}/{total_files} news files indexed successfully.")
    return docs


def build_vectorstore_news():
    """Build FAISS vectorstore for pure news files."""
    settings = get_settings()
    client_id = settings.bot_profile.strip()

    # 🔹 Input root = INDEX_FILES_ROOT_PATH
    base_docs_path = Path(settings.index_files_root_path).expanduser().resolve()
    doc_path = base_docs_path / client_id

    # 🔹 Output root = BOT_PROFILE_ROOT_PATH
    base_vectorstore_path = Path(settings.bot_profile_root_path).expanduser().resolve()
    vectorstore_path = base_vectorstore_path / client_id

    if not doc_path.exists():
        raise FileNotFoundError(f"❌ News folder not found: {doc_path}")

    print(f"📂 Loading news documents from: {doc_path}")
    raw_docs = load_news_documents(str(doc_path))
    if not raw_docs:
        print("⚠️ No documents found.")
        return

    documents = _split_docs(raw_docs)
    print(f"🧩 Produced {len(documents)} chunks for embedding.")

    embeddings = OpenAIEmbeddings()
    vectordb = FAISS.from_documents(documents, embeddings)

    vectorstore_path.mkdir(parents=True, exist_ok=True)
    vectordb.save_local(str(vectorstore_path))

    if documents:
        print(f"✅ Example metadata sample: {documents[0].metadata}")

    print(f"✅ Vectorstore saved to: {vectorstore_path}")


if __name__ == "__main__":
    build_vectorstore_news()
