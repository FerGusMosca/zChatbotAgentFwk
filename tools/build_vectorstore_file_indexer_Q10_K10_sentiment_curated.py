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


# =====================================================================
# HELPERS
# =====================================================================

def _clean_text(text: str) -> str:
    """Clean invisible chars and normalize spacing."""
    return " ".join(text.replace("\u200b", "").split())


def _split_docs(docs: List[Document]) -> List[Document]:
    """Split documents for embedding."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=80,
        separators=[". ", "\n", " "]
    )
    chunks = []
    for d in docs:
        parts = splitter.split_text(_clean_text(d.page_content))
        for i, p in enumerate(parts):
            meta = dict(d.metadata)
            meta["chunk"] = i
            chunks.append(Document(page_content=p, metadata=meta))
    return chunks


def extract_file_metadata(path: str) -> dict:
    """Infer metadata like symbol, period, year, report type."""
    fname = os.path.basename(path)
    parts = fname.replace(".json", "").split("_")
    meta = {"symbol": None, "period": None, "year": None, "report_type": None}

    for part in parts:
        up = part.upper()
        if up in ("Q1", "Q2", "Q3", "Q4"):
            meta["period"] = up
        elif up.startswith("Y20") or up.isdigit():
            meta["year"] = up
        elif up in ("10K", "10Q", "8K"):
            meta["report_type"] = up
        elif len(up) <= 5 and up.isalpha():
            meta["symbol"] = up
    return meta


# =====================================================================
# LOAD FILES
# =====================================================================

def load_file_index_documents(base_folder: str) -> list[Document]:
    """Load JSON files recursively and create semantic document entries."""
    docs = []
    base_root = Path(get_settings().index_files_root_path or base_folder).resolve()

    for root, _, files in os.walk(base_folder):
        for f in files:
            if not f.lower().endswith(".json"):
                continue
            full_path = Path(root) / f
            rel_path = str(full_path.relative_to(base_root))

            with open(full_path, "r", encoding="utf-8") as fp:
                content = fp.read()

            snippet = content[:2000]
            meta = extract_file_metadata(full_path)
            meta["filename"] = f
            meta["path"] = rel_path

            meta_text = (
                f"Document context:\n"
                f"- Company: {meta.get('symbol', 'N/A')}\n"
                f"- Report type: {meta.get('report_type', 'N/A')} (e.g. Q10 or K10)\n"
                f"- Fiscal year: {meta.get('year', 'N/A')}\n"
                f"- Period: {meta.get('period', 'N/A')}\n"
                f"- Theme: Sentiment Analysis (curated file)\n"
                f"This text summarizes the Management Discussion and Analysis (MD&A) section "
                f"for the given company and time period.\n\n"
            )

            docs.append(Document(page_content=meta_text + snippet, metadata=meta))
            print(f"✅ Indexed {rel_path}")

    print(f"📊 Indexed {len(docs)} total files.")
    return docs


# =====================================================================
# MAIN BUILDER
# =====================================================================

def build_vectorstore_file_indexer():
    """
    Build FAISS vectorstore for semantic file retrieval.
    ✅ Input:
        data/documents/<bot_profile>/Q10_sentiment_summary_report
        data/documents/<bot_profile>/K10_sentiment_summary_report
    ✅ Output:
        BOT_PROFILE_ROOT_PATH/<bot_profile>
    """
    settings = get_settings()
    client_id = settings.bot_profile  # 👈 tomado dinámicamente
    docs_root = Path(settings.index_files_root_path).expanduser().resolve()
    bot_root_path = Path(settings.bot_profile_root_path).expanduser().resolve()

    base_docs_path = docs_root / client_id
    all_docs = []

    for subfolder in ["Q10_sentiment_summary_report", "K10_sentiment_summary_report"]:
        docs_path = base_docs_path / subfolder
        if docs_path.exists():
            print(f"📂 Loading documents from {docs_path}")
            all_docs.extend(load_file_index_documents(str(docs_path)))
        else:
            print(f"⚠️ Skipping missing folder: {docs_path}")

    if not all_docs:
        raise FileNotFoundError(f"No documents found under {base_docs_path}")

    print(f"🧩 Total documents collected: {len(all_docs)}")

    split_docs = _split_docs(all_docs)
    embeddings = OpenAIEmbeddings()

    # ✅ Save FAISS in BOT_PROFILE_ROOT_PATH/<client_id>
    vect_path = bot_root_path / client_id
    vect_path.mkdir(parents=True, exist_ok=True)

    vectordb = FAISS.from_documents(split_docs, embeddings)
    vectordb.save_local(str(vect_path))

    print(f"✅ Vectorstore saved to: {vect_path}")


# =====================================================================
# ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    build_vectorstore_file_indexer()
