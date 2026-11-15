"""Lossless event snapshots sharing immutable blocks within one run.

Legacy JSON arrays/JSONL remain readable. New session snapshots contain a small
index; the run's event-store directory must travel with them in an archive.
Nothing in this module changes game events or model-visible feedback.
"""
from __future__ import annotations

import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import uuid4

FORMAT = 'memorybenchmark-event-blocks-1'
BLOCK_EVENTS = 32
STORE = '../../event-store'


def _atomic(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_events(path, events):
    """Save a complete logical history without copying its prefix per task."""
    path = Path(path)
    store = path.parent.parent.parent / 'event-store'
    store.mkdir(parents=True, exist_ok=True)
    if store.is_symlink() or getattr(store, 'is_junction', lambda: False)():
        raise ValueError('Event store must be an ordinary run directory')
    chunks, count, whole, block = [], 0, sha256(), []

    def publish():
        body = b''.join(block)
        digest = sha256(body).hexdigest()
        blob = store / (digest + '.jsonl.gz')
        if not blob.exists():
            temporary = blob.with_name(blob.name + '.' + uuid4().hex + '.tmp')
            try:
                temporary.write_bytes(gzip.compress(body, compresslevel=6, mtime=0))
                try:
                    os.link(temporary, blob)  # publish once, including concurrent branches
                except FileExistsError:
                    pass
            finally:
                temporary.unlink(missing_ok=True)
        chunks.append({'sha256': digest, 'bytes': len(body), 'events': len(block)})

    for event in events:
        line = (json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
        whole.update(line)
        block.append(line)
        count += 1
        if len(block) == BLOCK_EVENTS:
            publish()
            block = []
    if block:
        publish()
    descriptor = {'format': FORMAT, 'store': STORE, 'events': count,
                  'sha256': whole.hexdigest(), 'chunks': chunks}
    _atomic(path, (json.dumps(descriptor, separators=(',', ':')) + '\n').encode('utf-8'))


def decode_events(body, blob_reader):
    """Decode legacy records or verify every referenced block and full index."""
    text = body.decode('utf-8-sig')
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(value, list):
        return value
    if not isinstance(value, dict) or value.get('format') != FORMAT:
        # A one-record legacy JSONL stream is a JSON object, too.
        return [value] if text.strip() else []
    if value.get('store') != STORE:
        raise ValueError('Invalid event-store location')
    whole, events = sha256(), []
    for chunk in value['chunks']:
        digest = chunk['sha256']
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid event-block identity')
        raw = gzip.decompress(blob_reader(digest + '.jsonl.gz'))
        if len(raw) != chunk['bytes'] or sha256(raw).hexdigest() != digest:
            raise ValueError('Event-block integrity mismatch')
        rows = [json.loads(line) for line in raw.splitlines()]
        if len(rows) != chunk['events']:
            raise ValueError('Event-block count mismatch')
        whole.update(raw)
        events.extend(rows)
    if len(events) != value['events'] or whole.hexdigest() != value['sha256']:
        raise ValueError('Event-snapshot integrity mismatch')
    return events


def read_events(path):
    path = Path(path)
    store = path.parent.parent.parent / 'event-store'
    def blob_reader(name):
        blob = store / name
        if store.is_symlink() or blob.is_symlink() or getattr(store, 'is_junction', lambda: False)():
            raise ValueError('Event blocks must remain within their own run')
        return blob.read_bytes()
    return decode_events(path.read_bytes(), blob_reader)


def read_archive_events(bundle, name):
    from posixpath import dirname, normpath, join
    def blob_reader(blob):
        store = normpath(join(dirname(name), STORE))
        if store.startswith('../') or store.startswith('/'):
            raise ValueError('Event-store location escapes archive')
        return bundle.read(store + '/' + blob)
    return decode_events(bundle.read(name), blob_reader)
