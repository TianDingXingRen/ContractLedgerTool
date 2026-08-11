"""Streaming file and binary-stream digest helpers."""

from __future__ import annotations

import hashlib


DEFAULT_DIGEST_CHUNK_SIZE = 1024 * 1024


def sha256_stream(stream, *, chunk_size=DEFAULT_DIGEST_CHUNK_SIZE):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(chunk_size), b''):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path, *, chunk_size=DEFAULT_DIGEST_CHUNK_SIZE):
    with open(path, 'rb') as stream:
        return sha256_stream(stream, chunk_size=chunk_size)
