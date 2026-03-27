"""ChromaDB client for invest_harness knowledge retrieval.

Two collections:
  - normalized_facts: structured facts from ingestion pipeline
  - curated_insights: distilled insights + consensus tracking
"""

import chromadb

COLLECTION_NORMALIZED = "normalized_facts"
COLLECTION_CURATED = "curated_insights"


class ChromaManager:
    """Manages ChromaDB collections for the knowledge layer."""

    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._normalized = self._client.get_or_create_collection(
            name=COLLECTION_NORMALIZED,
            metadata={"hnsw:space": "cosine"},
        )
        self._curated = self._client.get_or_create_collection(
            name=COLLECTION_CURATED,
            metadata={"hnsw:space": "cosine"},
        )

    def list_collections(self) -> list[str]:
        return [c.name for c in self._client.list_collections()]

    # --- Normalized Facts ---

    def add_fact(self, fact_id: str, text: str, metadata: dict) -> None:
        self._normalized.upsert(
            ids=[fact_id],
            documents=[text],
            metadatas=[metadata],
        )

    def search_facts(
        self, query: str, n_results: int = 10, where: dict | None = None
    ) -> list[dict]:
        if self._normalized.count() == 0:
            return []
        kwargs = {"query_texts": [query], "n_results": min(n_results, self._normalized.count())}
        if where:
            kwargs["where"] = where
        results = self._normalized.query(**kwargs)
        return self._format_results(results)

    def delete_fact(self, fact_id: str) -> None:
        self._normalized.delete(ids=[fact_id])

    def update_fact_metadata(self, fact_id: str, metadata_update: dict) -> None:
        existing = self._normalized.get(ids=[fact_id])
        if not existing["ids"]:
            return
        current_meta = existing["metadatas"][0]
        current_meta.update(metadata_update)
        self._normalized.update(ids=[fact_id], metadatas=[current_meta])

    # --- Curated Insights ---

    def add_insight(self, insight_id: str, text: str, metadata: dict) -> None:
        self._curated.upsert(
            ids=[insight_id],
            documents=[text],
            metadatas=[metadata],
        )

    def search_insights(
        self, query: str, n_results: int = 10, where: dict | None = None
    ) -> list[dict]:
        if self._curated.count() == 0:
            return []
        kwargs = {"query_texts": [query], "n_results": min(n_results, self._curated.count())}
        if where:
            kwargs["where"] = where
        results = self._curated.query(**kwargs)
        return self._format_results(results)

    def delete_insight(self, insight_id: str) -> None:
        self._curated.delete(ids=[insight_id])

    # --- Maintenance ---

    def clear_collection(self, collection_name: str) -> None:
        coll = self._client.get_collection(collection_name)
        if coll.count() > 0:
            all_ids = coll.get()["ids"]
            coll.delete(ids=all_ids)

    @staticmethod
    def _format_results(results: dict) -> list[dict]:
        """Convert ChromaDB query results to a flat list of dicts."""
        formatted = []
        if not results["ids"] or not results["ids"][0]:
            return []
        for i, doc_id in enumerate(results["ids"][0]):
            entry = {
                "id": doc_id,
                "document": results["documents"][0][i] if results["documents"] else None,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else None,
            }
            if results.get("distances"):
                entry["distance"] = results["distances"][0][i]
            formatted.append(entry)
        return formatted
