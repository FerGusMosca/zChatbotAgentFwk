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
    """Remove invisible characters and normalize whitespace."""
    return " ".join(text.replace("\u200b", "").split())


def _split_docs(docs: List[Document]) -> List[Document]:
    """Split large documents into chunks for embedding."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=700,
        chunk_overlap=100,
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


def extract_file_metadata(path: Path) -> dict:
    """Extract metadata (symbol, year, period, report_type) from filename."""
    fname = path.name.replace(".json", "")
    parts = fname.split("_")

    meta = {
        "symbol": None,
        "period": None,
        "year": None,
        "report_type": None,
    }

    for part in parts:
        up = part.upper()
        if up.startswith("Q") and len(up) <= 3:  # Q1, Q2, Q3, Q4
            meta["period"] = up
            meta["report_type"] = "Q10"
        elif up.startswith("Y20") or up.isdigit():
            meta["year"] = up
        elif up in ("10K", "K10"):
            meta["report_type"] = "K10"
        elif len(up) <= 5 and up.isalpha():
            meta["symbol"] = up

    return meta


# =====================================================================
# MAIN LOADER
# =====================================================================

def load_rag_curated_documents(base_folder: Path) -> List[Document]:
    """Recursively load curated sentiment JSONs for Q10/K10 filings."""
    docs = []
    total = 0

    for root, _, files in os.walk(base_folder):
        for f in files:
            if not f.lower().endswith(".json"):
                continue

            file_path = Path(root) / f
            meta = extract_file_metadata(file_path)

            with open(file_path, "r", encoding="utf-8") as fp:
                try:
                    content = fp.read()
                except Exception:
                    continue

            snippet = content[:3000]  # Limit to avoid huge embeddings

            # 🧠 Textual embedding context — reinforce exact filename & attributes
            page_text = (
                f"Filing summary for {meta.get('symbol')} - "
                f"{meta.get('report_type', 'N/A')} "
                f"{meta.get('period', '')} {meta.get('year', '')}. "
                f"This document corresponds to the Management Discussion and Analysis (MD&A) "
                f"section of the company's official filing. "
                f"Filename: {f}. Full text follows:\n\n{snippet}"
            )

            meta["filename"] = f
            meta["path"] = str(file_path.relative_to(base_folder))

            docs.append(Document(page_content=page_text, metadata=meta))
            total += 1

    print(f"✅ Indexed {total} curated RAG documents.")
    return docs


# =====================================================================
# MAIN BUILDER
# =====================================================================

def build_vectorstore_file_indexer_Q10_K10_RAG_curated():
    """
    Build FAISS index for curated RAG Q10/K10 sentiment JSONs.
    ✅ Input:
        INDEX_FILES_ROOT_PATH / BOT_PROFILE / **/*.json
    ✅ Output:
        BOT_PROFILE_ROOT_PATH / BOT_PROFILE
    """
    settings = get_settings()
    bot_profile = settings.bot_profile
    index_root = Path(settings.index_files_root_path).expanduser().resolve()
    bot_root = Path(settings.bot_profile_root_path).expanduser().resolve()

    base_docs_path = index_root / bot_profile
    if not base_docs_path.exists():
        raise FileNotFoundError(f"❌ Missing path: {base_docs_path}")

    print(f"📂 Scanning recursively in: {base_docs_path}")
    all_docs = load_rag_curated_documents(base_docs_path)

    if not all_docs:
        raise FileNotFoundError(f"No JSON files found under {base_docs_path}")

    print(f"🧩 Total documents collected: {len(all_docs)}")

    split_docs = _split_docs(all_docs)
    embeddings = OpenAIEmbeddings()

    # ✅ Save FAISS in BOT_PROFILE_ROOT_PATH / BOT_PROFILE
    vect_path = bot_root / bot_profile
    vect_path.mkdir(parents=True, exist_ok=True)

    vectordb = FAISS.from_documents(split_docs, embeddings)
    vectordb.save_local(str(vect_path))

    print(f"✅ Vectorstore (RAG curated) saved to: {vect_path}")


# =====================================================================
# ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    build_vectorstore_file_indexer_Q10_K10_RAG_curated()
