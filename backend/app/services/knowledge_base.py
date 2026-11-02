"""The green coding knowledge base: knowledge_base/practices.json."""

import hashlib
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

PRACTICES_FILE = Path(__file__).resolve().parent.parent / "knowledge_base" / "practices.json"


class Practice(BaseModel):
    id: str
    title: str
    category: str
    content: str

    def document_text(self) -> str:
        """The text that is indexed for retrieval."""
        return f"{self.title}. Category: {self.category}. {self.content}"


def load_practices(path: Path = PRACTICES_FILE) -> list[Practice]:
    practices = TypeAdapter(list[Practice]).validate_json(path.read_bytes())
    ids = [p.id for p in practices]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"Duplicate practice ids in {path.name}: {duplicates}")
    return practices


def fingerprint(practices: list[Practice], *extra: str) -> str:
    """Changes whenever the practices (or anything in `extra`) change."""
    digest = hashlib.sha256()
    for part in [*(p.model_dump_json() for p in practices), *extra]:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:32]
