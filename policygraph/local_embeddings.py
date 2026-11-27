"""Offline embeddings from an already-present SentenceTransformer snapshot."""
from __future__ import annotations

import hashlib
import inspect
import os
from pathlib import Path


def model_fingerprint(path):
    path = Path(path).expanduser().resolve()
    if not path.is_dir() or not (path / "config.json").exists() or not (path / "modules.json").exists():
        raise ValueError("Use a complete local SentenceTransformer snapshot directory")
    files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in {".json", ".txt", ".bin", ".safetensors"})
    if not any(p.suffix in {".bin", ".safetensors"} for p in files):
        raise ValueError("Local model weights missing")
    hasher = hashlib.sha256()
    for file in files:
        hasher.update(str(file.relative_to(path)).encode())
        with file.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
    return path, hasher.hexdigest()


class LocalEncoder:
    def __init__(self, path):
        self.path, self.fingerprint = model_fingerprint(path)
        # Set before importing either package. Never resolve a repository ID online.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        import torch
        from sentence_transformers import SentenceTransformer
        torch.set_num_threads(4)
        kwargs = {"device": "cpu", "trust_remote_code": False}
        if "local_files_only" in inspect.signature(SentenceTransformer).parameters:
            kwargs["local_files_only"] = True
        self.model = SentenceTransformer(str(self.path), **kwargs)
        self.usage = {"requests": 0, "local_texts_encoded": 0}

    @property
    def identity(self):
        return {"kind": "local_sentence_transformer", "model": str(self.path), "fingerprint": self.fingerprint,
                "normalize_embeddings": True, "max_seq_length": self.model.max_seq_length}

    def embeddings(self, texts):
        self.usage["local_texts_encoded"] += len(texts)
        return self.model.encode(texts, batch_size=16, show_progress_bar=False, normalize_embeddings=True).tolist()
