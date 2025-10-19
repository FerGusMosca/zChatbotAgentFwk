import os
import json
import pandas as pd
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from common.config.settings import get_settings

load_dotenv()

# ========== HELPERS =============================================================

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


# ========== LOADERS =============================================================

def load_sentiment_rankings(folder_path: str) -> List[Document]:
    """Load sentiment ranking data from CSVs, recursively across subfolders."""
    docs = []
    total = 0

    for root, _, files in os.walk(folder_path):
        for file in files:
            if not file.lower().endswith(".csv"):
                continue

            csv_path = os.path.join(root, file)
            try:
                df = pd.read_csv(csv_path)
                for _, row in df.iterrows():
                    symbol = row.get("symbol")
                    year = row.get("year")
                    report_type = row.get("report_type")
                    mdna = row.get("sentiment_mdna")
                    outlook = row.get("sentiment_outlook")
                    forward = row.get("forward_ratio")
                    hedge = row.get("hedge_ratio")
                    optimism = row.get("optimism_score")

                    # 🧠 Semantically rich text for embeddings
                    content = (
                        f"This document summarizes financial sentiment indicators for {symbol} "
                        f"in its {year} {report_type} filings. "
                        f"The Management Discussion & Analysis (MD&A) sentiment score is {mdna}. "
                        f"The outlook sentiment score is {outlook}. "
                        f"The forward ratio is {forward}, while the hedge ratio is {hedge}. "
                        f"The overall optimism score is {optimism}."
                    )

                    docs.append(
                        Document(
                            page_content=content,
                            metadata={
                                "symbol": symbol,
                                "year": year,
                                "report_type": report_type,
                                "source": file,
                                "path": root,
                                "type": "ranking",
                            },
                        )
                    )
                    total += 1
            except Exception as e:
                print(f"❌ Error reading {csv_path}: {e}")

    print(f"✅ Indexed {total} ranking entries from CSV (recursive).")
    return docs




def load_sentiment_contexts(folder_path: str) -> List[Document]:
    """Load contextual data from JSON summaries (qualitative layer)."""
    docs = []
    total_files = 0
    processed = 0

    for root, _, files in os.walk(folder_path):
        for filename in files:
            total_files += 1
            if not filename.lower().endswith(".json"):
                continue
            path = os.path.join(root, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for entry in data:
                        text = entry.get("curated_text") or json.dumps(entry)
                        if not text or len(text.strip()) < 50:
                            continue
                        content = (
                            f"Symbol: {entry.get('symbol')}. Year: {entry.get('year')}. "
                            f"ReportType: {entry.get('report_type')}. "
                            f"Full text: {text}"
                        )
                        docs.append(
                            Document(
                                page_content=content,
                                metadata={
                                    "symbol": entry.get("symbol"),
                                    "year": entry.get("year"),
                                    "report_type": entry.get("report_type"),
                                    "source": filename,
                                    "type": "context"
                                },
                            )
                        )
                        processed += 1
            except Exception as e:
                print(f"❌ Error reading {filename}: {e}")
    print(f"✅ Indexed {processed}/{total_files} contextual JSON files.")
    return docs


# ========== MAIN BUILDER =============================================================

def build_vectorstore_sentiment_hybrid():
    """Hybrid Vectorstore combining rankings (CSV) + contextual summaries (JSON)."""
    settings = get_settings()

    # Build full client_id path (root + profile)
    bot_profile = settings.bot_profile
    bot_root_path = settings.bot_profile_root_path
    client_id = str(Path(bot_root_path) / bot_profile)

    # Use the same structure as HybridBot loader
    repo_root = Path(__file__).resolve().parents[1]
    doc_path = repo_root / "data" / "documents" / bot_profile
    vectorstore_path = Path(client_id).expanduser().resolve()

    if not doc_path.exists():
        raise FileNotFoundError(f"❌ Folder not found: {doc_path}")

    print(f"📂 Loading hybrid sentiment documents from: {doc_path}")
    rank_docs = load_sentiment_rankings(str(doc_path))
    context_docs = load_sentiment_contexts(str(doc_path))

    all_docs = rank_docs + context_docs
    print(f"🧩 Combined total: {len(all_docs)} documents.")

    documents = _split_docs(all_docs)

    embeddings = OpenAIEmbeddings()
    vectordb = FAISS.from_documents(documents, embeddings)

    # Save directly to the full path
    vectorstore_path.mkdir(parents=True, exist_ok=True)
    vectordb.save_local(str(vectorstore_path))

    print(f"✅ Example metadata sample: {documents[0].metadata}")
    print(f"✅ Hybrid vectorstore saved to: {vectorstore_path}")


# ========== ENTRY POINT =============================================================

if __name__ == "__main__":
    build_vectorstore_sentiment_hybrid()
