"""Disk-backed SSE evidence and a bounded-chunk local worker transport.

Only transport changes: the native client receives every original SSE byte.
No model request, event, prompt, tool, token budget or memory content is edited.
"""
import base64
from hashlib import sha256
import json
from pathlib import Path
import tempfile


CHUNK_BYTES = 64 * 1024
PROTOCOL = "rpc-sse-chunks-1"


class SpoolLines(list):
    """A JSON-array-compatible view; never retain the whole SSE stream in RAM."""
    def __init__(self, path, *, size, digest, line_count, owner=None):
        self.path = Path(path)
        self.size, self.digest, self.line_count = size, digest, line_count
        self.owner = owner
        self.readers = set()

    def __len__(self):
        return self.line_count

    def __iter__(self):
        with self.path.open("rb") as stream:
            self.readers.add(stream)
            try:
                for line in stream:
                    yield line.decode("utf-8").rstrip("\r\n")
            finally:
                self.readers.discard(stream)

    def __getitem__(self, index):
        # Compatibility for small diagnostic callers. Production serializes
        # by iteration and forwards fixed-size bytes rather than indexing.
        if isinstance(index, slice):
            return list(self)[index]
        if index < 0:
            index += len(self)
        for at, value in enumerate(self):
            if at == index:
                return value
        raise IndexError(index)

    def __eq__(self, other):
        return list(self) == other

    def close(self):
        for stream in tuple(self.readers):
            stream.close()
        self.readers.clear()
        if self.owner is not None:
            self.owner.cleanup()
            self.owner = None

    def __del__(self):
        self.close()

    def iter_bytes(self):
        with self.path.open("rb") as stream:
            self.readers.add(stream)
            try:
                for block in iter(lambda: stream.read(CHUNK_BYTES), b""):
                    yield block
            finally:
                self.readers.discard(stream)


def send_rpc(stream, value, check=None):
    """Keep model streams out of a single enormous JSON RPC message."""
    def write(message):
        if check:
            check()
        json.dump(message, stream, ensure_ascii=False)
        stream.write("\n")
        stream.flush()

    lines = (value.get("result") or {}).get("lines") if isinstance(value.get("result"), dict) else None
    if not isinstance(lines, SpoolLines):
        write(value)
        return
    identity = value["id"]
    write({"id": identity, "result_stream": {
        "protocol": PROTOCOL, "bytes": lines.size, "sha256": lines.digest}})
    sequence = 0
    for sequence, block in enumerate(lines.iter_bytes(), 1):
        write({"id": identity, "stream_chunk": sequence,
               "data": base64.b64encode(block).decode("ascii")})
    write({"id": identity, "stream_end": sequence})


class RPCStreamLines:
    """Consume host chunks directly; native tools never see host spool files.

    The owning Wire lock stays held until the stream ends or is drained by
    close(), so background native requests cannot interleave RPC replies.
    """
    def __init__(self, stream, identity, metadata, release):
        if metadata.get("protocol") != PROTOCOL:
            raise RuntimeError("Unsupported model stream framing")
        self.stream, self.identity = stream, identity
        self.expected_size, self.expected_hash = metadata["bytes"], metadata["sha256"]
        self.release, self.finished = release, False
        self.sequence, self.size, self.digest = 0, 0, sha256()

    def _finish(self):
        if not self.finished:
            self.finished = True
            self.release()

    def _chunks(self):
        try:
            while not self.finished:
                raw = self.stream.readline()
                if not raw:
                    raise RuntimeError("Runner disconnected during model stream")
                value = json.loads(raw)
                if value.get("id") != self.identity:
                    raise RuntimeError("Model stream RPC identity mismatch")
                if "stream_end" in value:
                    if (value["stream_end"] != self.sequence or self.size != self.expected_size
                            or self.digest.hexdigest() != self.expected_hash):
                        raise RuntimeError("Model stream size or SHA mismatch")
                    self._finish()
                    return
                if value.get("stream_chunk") != self.sequence + 1:
                    raise RuntimeError("Model stream sequence mismatch")
                block = base64.b64decode(value["data"], validate=True)
                if len(block) > CHUNK_BYTES:
                    raise RuntimeError("Invalid model stream chunk")
                self.sequence += 1
                self.size += len(block)
                self.digest.update(block)
                yield block
        except BaseException:
            self._finish()
            raise

    def iter_bytes(self):
        yield from self._chunks()
        # The host returns at response.completed, before a trailing empty SSE
        # line may have arrived. Preserve the old client's terminal delimiter.
        yield b"\n\n"

    def __iter__(self):
        fragments = []
        for block in self._chunks():
            pieces = block.split(b"\n")
            for part in pieces[:-1]:
                fragments.append(part)
                yield b"".join(fragments).decode("utf-8").rstrip("\r")
                fragments.clear()
            if pieces[-1]:
                fragments.append(pieces[-1])
        if fragments:
            yield b"".join(fragments).decode("utf-8").rstrip("\r")

    def close(self):
        # A native client can stop reading immediately after the completed
        # event. Drain only the remaining transport envelope, never run a tool.
        for _ in self._chunks():
            pass


class ReceivedStreamLines(SpoolLines):
    """Worker-private spool; native tool threads never wait for a stream lock."""
    finished = True

    def iter_bytes(self):
        yield from super().iter_bytes()
        yield b"\n\n"


def receive_rpc_stream(stream, identity, metadata, release):
    """Finish the bounded transport before giving native parsers the response.

    Native GA can stop iterating at response.completed and then dispatch a tool
    on a different thread. Keeping the RPC lock until that iterator closes
    would deadlock its tool broker. Spooling inside the sandbox releases the
    lock before native code runs, without buffering the response in memory.
    """
    try:
        incoming = RPCStreamLines(stream, identity, metadata, release)
    except BaseException:
        release()
        raise
    owner = tempfile.TemporaryDirectory(prefix="native-model-stream-")
    path = Path(owner.name) / "response.sse"
    try:
        count = 0
        with path.open("wb") as target:
            for block in incoming._chunks():
                target.write(block)
                count += block.count(b"\n")
        return ReceivedStreamLines(path, size=incoming.size,
                                   digest=incoming.digest.hexdigest(), line_count=count, owner=owner)
    except BaseException:
        incoming._finish()
        owner.cleanup()
        raise


def forwarded_httpx_response(httpx, request, lines, *, streaming):
    """Match Client.send's eager/streaming contract without changing SSE."""
    class ForwardedStream(httpx.SyncByteStream):
        def __iter__(self): return lines.iter_bytes()
        def close(self): lines.close()
    response = httpx.Response(200, headers={"content-type": "text/event-stream"},
                              stream=ForwardedStream(), request=request)
    if not streaming:
        response.read()
    return response
