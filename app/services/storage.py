import re
from pathlib import Path

from app.core.errors import DomainError


class StorageService:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, key: str, data: bytes) -> None:
        path = self.resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        path = self.resolve(key)
        if not path.is_file():
            raise DomainError("FILE_NOT_FOUND", "File was not found.", 404)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self.resolve(key)
        if path.is_file():
            path.unlink()

    def resolve(self, key: str) -> Path:
        if not key or key.startswith(("/", "\\")) or ".." in Path(key).parts:
            raise DomainError("INVALID_STORAGE_KEY", "Invalid storage key.", 400)
        path = (self.root / key).resolve()
        if self.root != path and self.root not in path.parents:
            raise DomainError("INVALID_STORAGE_KEY", "Invalid storage key.", 400)
        return path


def safe_filename(name: str) -> str:
    base = Path(name or "file").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:120]
    return cleaned or "file"
