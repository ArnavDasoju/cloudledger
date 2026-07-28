"""RAG retrieval layer — indexes markdown docs into ChromaDB and retrieves relevant chunks."""

import os
import hashlib
import logging
from pathlib import Path
from typing import List, Dict

import chromadb

logger = logging.getLogger(__name__)

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_store")
COLLECTION_NAME = "cloudledger_docs"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def _get_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=CHROMA_DIR)


def _get_collection(client: chromadb.ClientAPI) -> chromadb.Collection:
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _chunk_text(text: str, source: str) -> List[Dict]:
    """Split text into overlapping chunks, preserving section headers as context."""
    lines = text.split("\n")
    chunks = []
    current_section = ""
    buffer = []
    buffer_len = 0

    for line in lines:
        # Track the nearest markdown header as section context
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            current_section = stripped.lstrip("#").strip()

        line_len = len(line)
        if buffer_len + line_len > CHUNK_SIZE and buffer:
            chunk_text = "\n".join(buffer)
            chunks.append({
                "text": chunk_text,
                "source": source,
                "section": current_section,
            })
            # Keep overlap: take lines from the end of the buffer
            overlap_lines = []
            overlap_len = 0
            for prev_line in reversed(buffer):
                if overlap_len + len(prev_line) > CHUNK_OVERLAP:
                    break
                overlap_lines.insert(0, prev_line)
                overlap_len += len(prev_line)
            buffer = overlap_lines
            buffer_len = overlap_len

        buffer.append(line)
        buffer_len += line_len

    if buffer:
        chunks.append({
            "text": "\n".join(buffer),
            "source": source,
            "section": current_section,
        })

    return chunks


def ingest_docs(docs_dir: str) -> Dict:
    """Index all markdown files from docs_dir into the vector store.

    Returns stats: {files, chunks, skipped}.
    """
    client = _get_client()
    collection = _get_collection(client)

    docs_path = Path(docs_dir)
    md_files = sorted(docs_path.glob("**/*.md"))

    if not md_files:
        logger.warning("No markdown files found in %s", docs_dir)
        return {"files": 0, "chunks": 0, "skipped": 0}

    total_chunks = 0
    skipped = 0

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        if not text.strip():
            skipped += 1
            continue

        source_name = str(md_file.relative_to(docs_path))
        chunks = _chunk_text(text, source_name)

        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.sha256(f"{source_name}:{i}:{chunk['text'][:100]}".encode()).hexdigest()[:16]
            ids.append(chunk_id)
            documents.append(chunk["text"])
            metadatas.append({"source": chunk["source"], "section": chunk["section"]})

        # Upsert so re-running is idempotent
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        total_chunks += len(chunks)
        logger.info("Indexed %s: %d chunks", source_name, len(chunks))

    return {"files": len(md_files), "chunks": total_chunks, "skipped": skipped}


MAX_DISTANCE = 1.2  # cosine distance threshold — discard chunks above this


def retrieve(query: str, n_results: int = 5) -> List[Dict]:
    """Retrieve the most relevant chunks for a query.

    Applies a distance threshold to filter out low-relevance results,
    and deduplicates near-identical chunks from overlapping windows.
    Returns list of {text, source, section, distance}.
    """
    client = _get_client()
    collection = _get_collection(client)

    if collection.count() == 0:
        logger.warning("Vector store is empty — run ingest first")
        return []

    # Fetch extra candidates so we still have enough after filtering
    results = collection.query(query_texts=[query], n_results=n_results + 3)

    raw = []
    for i in range(len(results["ids"][0])):
        dist = results["distances"][0][i] if results.get("distances") else 0
        if dist > MAX_DISTANCE:
            continue
        raw.append({
            "text": results["documents"][0][i],
            "source": results["metadatas"][0][i]["source"],
            "section": results["metadatas"][0][i]["section"],
            "distance": dist,
        })

    # Deduplicate overlapping chunks: if two chunks share >50% of their text, keep the closer one
    deduped = []
    for chunk in raw:
        is_dup = False
        chunk_words = set(chunk["text"].split())
        for existing in deduped:
            existing_words = set(existing["text"].split())
            overlap = len(chunk_words & existing_words)
            smaller = min(len(chunk_words), len(existing_words))
            if smaller > 0 and overlap / smaller > 0.5:
                is_dup = True
                break
        if not is_dup:
            deduped.append(chunk)
        if len(deduped) >= n_results:
            break

    return deduped


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    docs_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "docs")
    stats = ingest_docs(docs_dir)
    print(f"Ingested {stats['files']} files, {stats['chunks']} chunks, {stats['skipped']} skipped")
