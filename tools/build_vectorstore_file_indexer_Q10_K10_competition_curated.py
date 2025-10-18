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
        elif up in ("10K", "10Q", "K10", "Q10"):
            meta["report_type"] = up
        elif len(up) <= 5 and up.isalpha():
            meta["symbol"] = up
    return meta


def load_file_index_documents(base_folder: str) -> list[Document]:
    """
    Load competition JSON files from Q10 and K10 folders,
    adding contextual metadata for each document.
    """
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

            snippet = content[:2000]  # preview for embedding context
            meta = extract_file_metadata(full_path)
            meta["filename"] = f
            meta["path"] = rel_path

            meta_text = (
                f"Document context:\n"
                f"- Company: {meta.get('symbol', 'N/A')}\n"
                f"- Report type: {meta.get('report_type', 'N/A')} (e.g. Q10 or K10)\n"
                f"- Fiscal year: {meta.get('year', 'N/A')}\n"
                f"- Period: {meta.get('period', 'N/A')}\n"
                f"- Theme: Competition Analysis (curated file)\n"
                f"This text summarizes the section about competition and market peers "
                f"mentioned in the 10-Q or 10-K filing for the given company and time period.\n\n"
            )

            docs.append(Document(page_content=meta_text + snippet, metadata=meta))
            print(f"✅ Indexed {rel_path}")

    print(f"📊 Indexed {len(docs)} total files.")
    return docs


def build_vectorstore_competition_indexer(client_id: str):
    """Build vectorstore to locate competition files efficiently by semantic or metadata similarity."""
    repo_root = Path(__file__).resolve().parents[1]

    # 🔧 Traverse both Q10 and K10 competition folders automatically
    base_docs_path = repo_root / "data" / "documents" / client_id
    all_docs = []

    for subfolder in ["Q10_competition_summary_report", "K10_competition_summary_report"]:
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
    vect_path = repo_root / "vectorstores" / f"{client_id}"
    vect_path.mkdir(parents=True, exist_ok=True)
    vectordb = FAISS.from_documents(split_docs, embeddings)
    vectordb.save_local(str(vect_path))
    print(f"✅ Vectorstore saved to: {vect_path}")


if __name__ == "__main__":
    client_id = get_settings().bot_profile
    build_vectorstore_competition_indexer(client_id)
