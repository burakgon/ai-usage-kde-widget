from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional


def atomic_write_private(
    path: Path,
    text: str,
    *,
    expected_text: Optional[str] = None,
) -> bool:
    """Atomically replace a private UTF-8 file if its contents are unchanged."""
    try:
        if expected_text is not None:
            current = path.read_text(encoding="utf-8")
            if current != expected_text:
                return False
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        return False

    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        return True
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except OSError:
            pass
        return False
