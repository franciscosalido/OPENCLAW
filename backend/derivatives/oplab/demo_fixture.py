"""Captura BOVA11 versionada e verificada antes de compor a demo."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

from backend.derivatives.oplab.transport import FixtureTransport
from backend.derivatives.provenance import Provenance

REPO_ROOT = Path(__file__).resolve().parents[3]
_DIRECTORY = Path("tests/fixtures/derivatives/synthetic")
_MANIFEST_SHA256 = "f6cc62023e9fb45bffe52af16c6c2c21b4319a3da9fb01bda7e912abf7ac46c9"


def _verified_bytes(directory_fd: int, name: str, digest: str) -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(name, flags, dir_fd=directory_fd), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("fixture_integrity")
        data = stream.read(64 * 1024)
        if hashlib.sha256(data).hexdigest() != digest or stream.read(1):
            raise ValueError("fixture_integrity")
        return data


class DemoFixture(FixtureTransport):
    """Serve apenas os bytes cobertos pelo manifesto fixado nesta versão."""

    def __init__(self, directory: Path, *, mixed: bool = False) -> None:
        if directory not in (_DIRECTORY, REPO_ROOT / _DIRECTORY):
            raise ValueError("fixture_directory")
        super().__init__(directory, provenance=Provenance.SYNTHETIC)
        self.registry_json: bytes | None = None
        with ExitStack() as stack:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            fd = os.open(REPO_ROOT, flags)
            stack.callback(os.close, fd)
            for part in _DIRECTORY.parts:
                fd = os.open(part, flags, dir_fd=fd)
                stack.callback(os.close, fd)
            manifest = json.loads(_verified_bytes(fd, "manifest.json", _MANIFEST_SHA256))
            if (manifest["provenance"], manifest["purpose"]) != ("synthetic", "test"):
                raise ValueError("fixture_provenance")
            self.valuation = datetime.fromisoformat(manifest["valuation"])
            self._files = {name: _verified_bytes(fd, name, entry["sha256"])
                           for name, entry in manifest["files"].items()}

            if mixed:
                mixed_fd = os.open("mixed", flags, dir_fd=fd)
                stack.callback(os.close, mixed_fd)
                additional = _verified_bytes(mixed_fd, "options.json",
                    "76fe6c540cebfdbb929aeab0b681f5b900236de4f702dfa3e0623f75b71cdaae")
                self.registry_json = _verified_bytes(mixed_fd, "registry.json",
                    "a68417b465fa9dcc8edc7a5e13b9ac2b66930e8dd6bec039ad00c79a6188a51f")
                name = "market_options_BOVA11.json"
                options = json.loads(self._files[name]) + json.loads(additional)
                self._files[name] = json.dumps(options, separators=(",", ":")).encode()

    def _payload(self, name: str) -> object:
        if name not in self._files:
            # Mesmo contrato do transporte base: fixture ausente vira ``NotFoundError``.
            raise FileNotFoundError(name)
        return json.loads(self._files[name])
