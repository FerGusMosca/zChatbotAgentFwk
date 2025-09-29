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
import json
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
    chunks: List[Document] = []
    for d in docs:
        parts = splitter.split_text(_clean(d.page_content))
        for i, p in enumerate(parts):
            meta = dict(d.metadata)
            meta["chunk"] = i
            chunks.append(Document(page_content=p, metadata=meta))
    return chunks

def load_json_curated(file_path: str) -> list[Document]:
    """
    Load a curated JSON file (sentiment or competition) into a list of LangChain Documents.
    Metadata includes symbol, year, and category.
    """
    docs = []
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    symbol = data.get("symbol")
    year = data.get("year")

    # Detect category based on filename convention
    filename = os.path.basename(file_path).lower()
    if "sentiment" in filename:
        category = "sentiment"
        # Build text content from sentiment fields
        text = " ".join(
            [p["sent"] for p in data.get("top_positive", [])] +
            [n["sent"] for n in data.get("top_negative", [])] +
            data.get("forward_snippets", [])
        )
    elif "competition" in filename:
        category = "competition"
        # Use competition summary if available
        text = data.get("competition_summary", "")
    else:
        category = "generic_json"
        text = json.dumps(data)

    if text.strip():
        docs.append(Document(
            page_content=text,
            metadata={"symbol": symbol, "year": year, "category": category}
        ))
    return docs

def load_documents_from_folder(folder_path: str) -> list[Document]:
    """
    Recursive loader: walks through all subfolders and loads supported files.
    """
    docs: list[Document] = []
    for root, _, files in os.walk(folder_path):
        for filename in files:
            full_path = os.path.join(root, filename)
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
                except Exception as e:
                    print(f"❌ Error loading DOCX {filename}: {e}")
            elif filename.lower().endswith(".json"):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Handle different possible JSON structures
                    if isinstance(data, str):
                        text = data
                    elif isinstance(data, list):
                        # Join list items into a single text block
                        text = "\n".join(
                            json.dumps(item) if isinstance(item, dict) else str(item)
                            for item in data
                        )
                    elif isinstance(data, dict):
                        # Dump dict as a string
                        text = json.dumps(data)
                    else:
                        text = str(data)

                    docs.append(Document(page_content=text, metadata={"source": filename}))

                except Exception as e:
                    print(f"❌ Error loading JSON {filename}: {e}")


            else:
                print(f"❌ Unsupported file format: {filename}")
    return docs

def build_vectorstore(client_id: str):
    # 🛠️ Normalize client_id to avoid hidden spaces or line breaks
    client_id = (client_id or "").strip()

    # 🛠️ Compute repo root and target paths
    repo_root = Path(__file__).resolve().parents[1]
    doc_path = repo_root / "data" / "documents" / client_id
    vectorstore_path = repo_root / "vectorstores" / client_id

    # 🛡️ Extra safety: fail early if documents folder does not exist
    if not doc_path.exists():
        raise FileNotFoundError(f"❌ Docs folder not found: {doc_path}")

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
