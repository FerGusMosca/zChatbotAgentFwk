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
    return " ".join(text.replace("\u200b", "").split())

def _split_docs(docs: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900, chunk_overlap=150,
        separators=["\n## ", "\n# ", "\n- ", "\n• ", "\n", " ", ""]
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
    """
    Extrae metadatos robustos desde el nombre y la ruta del archivo.
    Ej: /.../Q10_sentiment_summary_report/2023/MSFT_2023_Q3_sentiment.json
    """
    fname = os.path.basename(file_path)
    parts = fname.split("_")

    meta = {"symbol": None, "year": None, "Period": None, "report_type": None}

    # 1️⃣ Symbol y año
    if len(parts) > 1:
        meta["symbol"] = parts[0]
        meta["year"] = parts[1]

    # 2️⃣ Trimestre o periodo
    for p in parts:
        if p.upper().startswith("Q") and len(p) <= 3:
            meta["Period"] = p.upper()

    # 3️⃣ Tipo de reporte (por carpeta o nombre)
    folder_name = Path(file_path).parent.name.lower()
    if "q10" in folder_name:
        meta["report_type"] = "10-Q"
    elif "k10" in folder_name:
        meta["report_type"] = "10-K"
    elif "sentiment" in folder_name:
        meta["report_type"] = "sentiment"
    else:
        meta["report_type"] = "other"

    return meta

def load_documents_from_folder(folder_path: str) -> list[Document]:
    docs = []
    for root, _, files in os.walk(folder_path):
        for filename in files:
            full_path = os.path.join(root, filename)
            if not filename.lower().endswith(".json"):
                continue

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict):
                    text = json.dumps(data)
                elif isinstance(data, list):
                    text = "\n".join(json.dumps(i) for i in data)
                else:
                    text = str(data)

                metadata = extract_metadata(full_path)
                metadata["source"] = filename
                docs.append(Document(page_content=text, metadata=metadata))

            except Exception as e:
                print(f"❌ Error loading {filename}: {e}")

    return docs

def build_vectorstore(client_id: str):
    client_id = (client_id or "").strip()
    repo_root = Path(__file__).resolve().parents[1]
    doc_path = repo_root / "data" / "documents" / client_id
    vectorstore_path = repo_root / "vectorstores" / client_id

    if not doc_path.exists():
        raise FileNotFoundError(f"❌ Docs folder not found: {doc_path}")

    print(f"📂 Loading documents recursively from: {doc_path}")
    raw_docs = load_documents_from_folder(str(doc_path))
    print(f"📄 Loaded {len(raw_docs)} documents total.")

    documents = _split_docs(raw_docs)
    print(f"🧩 Produced {len(documents)} chunks.")

    embeddings = OpenAIEmbeddings()
    vectordb = FAISS.from_documents(documents, embeddings)
    vectorstore_path.mkdir(parents=True, exist_ok=True)
    vectordb.save_local(str(vectorstore_path))

    # show one metadata sample
    if documents:
        print(f"✅ Example metadata sample: {documents[0].metadata}")

    print(f"✅ Vectorstore saved to: {vectorstore_path}")

if __name__ == "__main__":
    client_id = get_settings().bot_profile
    build_vectorstore(client_id)
