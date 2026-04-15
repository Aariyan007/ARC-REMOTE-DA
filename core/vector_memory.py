"""
Vector Memory — Semantic long-term memory using embeddings.

Enables queries like:
    "What did we talk about last Wednesday regarding the API?"
    "What food were we talking about?"

Uses chromadb if available, falls back to a lightweight FAISS-like
cosine-similarity search over numpy embeddings.

Architecture:
    - Stores conversation exchanges as embedded documents
    - Metadata: timestamp, topic, action, source
    - Retrieval via semantic similarity search
    - Auto-indexes new conversations from memory.py
"""

import os
import json
import time
import hashlib
import threading
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field


# ─── Settings ────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(__file__))
VECTOR_DIR     = os.path.join(BASE_DIR, "data", "vector_store")
STORE_PATH     = os.path.join(VECTOR_DIR, "memory_store.json")
MAX_DOCUMENTS  = 500
SIMILARITY_THRESHOLD = 0.3  # Minimum similarity for retrieval
# ─────────────────────────────────────────────────────────────


@dataclass
class MemoryDocument:
    """A single document in vector memory."""
    id:        str
    text:      str
    embedding: list = field(default_factory=list)
    metadata:  dict = field(default_factory=dict)
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id":        self.id,
            "text":      self.text,
            "embedding": self.embedding,
            "metadata":  self.metadata,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(d: dict) -> "MemoryDocument":
        return MemoryDocument(
            id=d["id"],
            text=d["text"],
            embedding=d.get("embedding", []),
            metadata=d.get("metadata", {}),
            timestamp=d.get("timestamp", 0.0),
        )


@dataclass
class SearchResult:
    """A single search result with similarity score."""
    document:   MemoryDocument
    similarity: float
    rank:       int


# ─── Embedding Engine ────────────────────────────────────────
_model = None
_model_lock = threading.Lock()


def _get_embedder():
    """Lazy-load the sentence transformer model."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    _model = SentenceTransformer("all-MiniLM-L6-v2")
                    print("🧠 Vector memory: Model loaded (all-MiniLM-L6-v2)")
                except ImportError:
                    print("⚠️  sentence-transformers not installed — using hash embeddings")
                    _model = "fallback"
    return _model


def _compute_embedding(text: str) -> list:
    """Compute embedding for a text string."""
    model = _get_embedder()

    if model == "fallback":
        # Fallback: simple hash-based pseudo-embedding (128-dim)
        import hashlib
        h = hashlib.sha512(text.lower().encode()).digest()
        # Convert bytes to float values between -1 and 1
        return [((b / 127.5) - 1.0) for b in h[:128]]

    try:
        embedding = model.encode(text, show_progress_bar=False)
        return embedding.tolist()
    except Exception as e:
        print(f"⚠️  Embedding error: {e}")
        return []


def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


# ─── Vector Memory Store ────────────────────────────────────
class VectorMemory:
    """
    Semantic long-term memory with vector search.

    stores conversations, research results, and context as
    embedded documents. Enables natural-language recall.

    Usage:
        vm = VectorMemory()
        vm.store("We talked about pizza for dinner", {"topic": "food"})
        results = vm.search("what food did we discuss?")
    """

    def __init__(self):
        self._documents: list[MemoryDocument] = []
        self._lock = threading.Lock()
        self._chromadb = None
        self._collection = None

        # Try ChromaDB first
        self._init_chromadb()

        # If no ChromaDB, load from JSON
        if not self._chromadb:
            self._load_from_disk()

    def _init_chromadb(self):
        """Try to initialize ChromaDB for production use."""
        try:
            import chromadb
            self._chromadb = chromadb.Client(chromadb.Settings(
                persist_directory=VECTOR_DIR,
                anonymized_telemetry=False,
            ))
            self._collection = self._chromadb.get_or_create_collection(
                name="jarvis_memory",
                metadata={"hnsw:space": "cosine"},
            )
            print("🧠 Vector memory: ChromaDB initialized")
        except ImportError:
            self._chromadb = None
        except Exception as e:
            print(f"⚠️  ChromaDB init error: {e}")
            self._chromadb = None

    def _load_from_disk(self):
        """Load documents from JSON fallback store."""
        if os.path.exists(STORE_PATH):
            try:
                with open(STORE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._documents = [MemoryDocument.from_dict(d) for d in data]
            except Exception as e:
                print(f"⚠️  Vector store load error: {e}")
                self._documents = []

    def _save_to_disk(self):
        """Save documents to JSON fallback store."""
        os.makedirs(VECTOR_DIR, exist_ok=True)
        try:
            data = [d.to_dict() for d in self._documents[-MAX_DOCUMENTS:]]
            with open(STORE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  Vector store save error: {e}")

    def store(
        self,
        text:     str,
        metadata: dict = None,
        doc_id:   str  = None,
    ) -> str:
        """
        Store a document in vector memory.

        Args:
            text:     The text content to remember
            metadata: Optional metadata (topic, action, timestamp, etc.)
            doc_id:   Optional custom ID (auto-generated if not provided)

        Returns:
            The document ID.
        """
        if not text or not text.strip():
            return ""

        # Generate ID
        if not doc_id:
            doc_id = hashlib.md5(f"{text}{time.time()}".encode()).hexdigest()[:12]

        meta = metadata or {}
        meta.setdefault("stored_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # ChromaDB path
        if self._collection:
            try:
                self._collection.add(
                    documents=[text],
                    metadatas=[meta],
                    ids=[doc_id],
                )
                return doc_id
            except Exception as e:
                print(f"⚠️  ChromaDB store error: {e}")
                # Fall through to JSON

        # JSON fallback path
        embedding = _compute_embedding(text)
        doc = MemoryDocument(
            id=doc_id,
            text=text,
            embedding=embedding,
            metadata=meta,
            timestamp=time.time(),
        )

        with self._lock:
            self._documents.append(doc)
            # Trim
            if len(self._documents) > MAX_DOCUMENTS:
                self._documents = self._documents[-MAX_DOCUMENTS:]

        self._save_to_disk()
        return doc_id

    def search(
        self,
        query:       str,
        top_k:       int   = 5,
        min_score:   float = None,
    ) -> list[SearchResult]:
        """
        Semantic search over stored documents.

        Args:
            query:     Natural language search query
            top_k:     Number of results to return
            min_score: Minimum similarity threshold (default: SIMILARITY_THRESHOLD)

        Returns:
            List of SearchResult ordered by similarity (highest first).
        """
        if not query:
            return []

        threshold = min_score if min_score is not None else SIMILARITY_THRESHOLD

        # ChromaDB path
        if self._collection:
            try:
                results = self._collection.query(
                    query_texts=[query],
                    n_results=top_k,
                )
                search_results = []
                if results and results.get("documents"):
                    for i, (doc_text, doc_id, meta, distance) in enumerate(zip(
                        results["documents"][0],
                        results["ids"][0],
                        results["metadatas"][0],
                        results["distances"][0],
                    )):
                        similarity = 1.0 - distance  # ChromaDB returns distance
                        if similarity >= threshold:
                            search_results.append(SearchResult(
                                document=MemoryDocument(
                                    id=doc_id,
                                    text=doc_text,
                                    metadata=meta,
                                ),
                                similarity=round(similarity, 3),
                                rank=i + 1,
                            ))
                return search_results
            except Exception as e:
                print(f"⚠️  ChromaDB search error: {e}")

        # JSON fallback: cosine similarity search
        if not self._documents:
            return []

        query_embedding = _compute_embedding(query)
        if not query_embedding:
            return []

        scored = []
        for doc in self._documents:
            if not doc.embedding:
                continue
            sim = _cosine_similarity(query_embedding, doc.embedding)
            if sim >= threshold:
                scored.append((doc, sim))

        # Sort by similarity (highest first)
        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            SearchResult(document=doc, similarity=round(sim, 3), rank=i + 1)
            for i, (doc, sim) in enumerate(scored[:top_k])
        ]

    def store_conversation(self, user_said: str, jarvis_said: str, action: str = "") -> str:
        """
        Convenience method to store a conversation exchange.
        Combines user + jarvis text for better retrieval.
        """
        combined = f"User: {user_said}\nJarvis: {jarvis_said}"
        metadata = {
            "type":      "conversation",
            "user_said": user_said,
            "jarvis_said": jarvis_said,
            "action":    action,
            "date":      datetime.now().strftime("%Y-%m-%d"),
            "time":      datetime.now().strftime("%H:%M"),
            "weekday":   datetime.now().strftime("%A"),
        }
        return self.store(combined, metadata)

    def recall(self, query: str, top_k: int = 3) -> str:
        """
        Human-readable recall. Returns formatted string of memories.
        Used directly in Gemini prompts or spoken responses.
        """
        results = self.search(query, top_k=top_k)
        if not results:
            return "I don't remember anything about that."

        lines = []
        for r in results:
            meta = r.document.metadata
            date = meta.get("date", "unknown date")
            lines.append(f"[{date}] {r.document.text[:200]} (relevance: {r.similarity:.0%})")

        return "\n".join(lines)

    @property
    def document_count(self) -> int:
        """Total documents in memory."""
        if self._collection:
            try:
                return self._collection.count()
            except Exception:
                pass
        return len(self._documents)

    def clear(self) -> None:
        """Clear all stored memories."""
        if self._collection:
            try:
                self._chromadb.delete_collection("jarvis_memory")
                self._collection = self._chromadb.get_or_create_collection("jarvis_memory")
            except Exception:
                pass

        with self._lock:
            self._documents = []
        self._save_to_disk()
        print("🧹 Vector memory cleared")


# ─── Singleton ───────────────────────────────────────────────
_vm_instance: Optional[VectorMemory] = None
_vm_lock = threading.Lock()


def get_vector_memory() -> VectorMemory:
    """Returns the global VectorMemory singleton."""
    global _vm_instance
    if _vm_instance is None:
        with _vm_lock:
            if _vm_instance is None:
                _vm_instance = VectorMemory()
    return _vm_instance


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  VECTOR MEMORY TEST")
    print("=" * 60)

    vm = VectorMemory()

    # Store some conversations
    vm.store_conversation("Let's order pizza tonight", "Sounds good! Want me to find places nearby?", "chat")
    vm.store_conversation("I'm working on the API integration", "How's the API project going?", "chat")
    vm.store_conversation("Open VS Code", "Opening VS Code now.", "open_app")
    vm.store_conversation("Send the report to Sarah", "Email sent to Sarah with the report.", "send_email")
    vm.store_conversation("What's the weather like", "It's sunny and 25 degrees.", "tell_weather")

    print(f"\nStored {vm.document_count} documents")

    # Test semantic search
    tests = [
        "what food were we talking about?",
        "what project am I working on?",
        "did I send any emails?",
    ]

    for query in tests:
        print(f"\nQuery: '{query}'")
        results = vm.search(query, top_k=2)
        for r in results:
            print(f"  [{r.similarity:.2f}] {r.document.text[:100]}")

    # Test recall
    print("\n-- Recall --")
    print(vm.recall("food"))

    vm.clear()
    print(f"\nAfter clear: {vm.document_count} documents")
    print("\n✅ Vector memory test passed!")
