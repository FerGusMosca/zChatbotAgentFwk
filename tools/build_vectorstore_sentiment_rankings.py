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
        chunk_size=800,
        chunk_overlap=120,
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


def load_sentiment_documents(folder_path: str) -> list[Document]:
    """Load all sentiment JSON files (consolidated + ranking)."""
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

                # Detect consolidated summary (list of dicts)
                if isinstance(data, list) and all(isinstance(x, dict) for x in data):
                    for entry in data:
                        symbol = entry.get("symbol")
                        metrics = entry.get("metrics", {})
                        text = entry.get("curated_text", "")
                        content = (
                            f"Symbol: {symbol}. Year: {entry.get('year')}. "
                            f"ReportType: {entry.get('report_type')}. "
                            f"MD&A Sentiment: {metrics.get('mdna_sentiment')}, "
                            f"Outlook Sentiment: {metrics.get('outlook_sentiment')}, "
                            f"Forward Ratio: {metrics.get('forward_ratio')}, "
                            f"Hedge Ratio: {metrics.get('hedge_ratio')}. "
                            f"Full text: {text}"
                        )
                        docs.append(Document(page_content=content, metadata={
                            "symbol": symbol,
                            "year": entry.get("year"),
                            "report_type": entry.get("report_type"),
                            "source": filename
                        }))
                        processed_files += 1
                else:
                    continue

                print(f"✅ [{processed_files}] Indexed: {filename}")

            except Exception as e:
                print(f"❌ Error loading {filename}: {e}")

    print(f"📊 Summary: {processed_files}/{total_files} sentiment files indexed successfully.")
    return docs


def build_vectorstore_sentiment(client_id: str):
    """Build FAISS vectorstore for sentiment ranking + summaries."""
    client_id = (client_id or "").strip()
    repo_root = Path(__file__).resolve().parents[1]
    doc_path = repo_root / "data" / "documents" / client_id
    vectorstore_path = repo_root / "vectorstores" / client_id

    if not doc_path.exists():
        raise FileNotFoundError(f"❌ Sentiment folder not found: {doc_path}")

    print(f"📂 Loading sentiment documents from: {doc_path}")
    raw_docs = load_sentiment_documents(str(doc_path))

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
    client_id = get_settings().bot_profile
    build_vectorstore_sentiment(client_id)
