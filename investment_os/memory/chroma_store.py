from pathlib import Path

import chromadb


class ThesisMemory:
    def __init__(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.collection = chromadb.PersistentClient(path=str(path)).get_or_create_collection(
            name="investment_theses"
        )

    def remember(self, memory_id: str, ticker: str, text: str) -> None:
        self.collection.upsert(ids=[memory_id], documents=[text], metadatas=[{"ticker": ticker.upper()}])

    def recall(self, ticker: str, query: str, limit: int = 5) -> list[str]:
        result = self.collection.query(
            query_texts=[query],
            n_results=limit,
            where={"ticker": ticker.upper()},
        )
        return result.get("documents", [[]])[0]
