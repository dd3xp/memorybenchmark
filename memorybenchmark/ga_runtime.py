"""Pristine native source, bounded memory snapshots and fail-closed WSL jail."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile


class IsolationError(RuntimeError):
    pass


def memory_manifest(root):
    """Reject links/special files; snapshots must not follow an agent out of jail."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("memory must be a real directory")
    result, total = {}, 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or getattr(path, "is_junction", lambda:False)():
            raise ValueError("memory links are not supported")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("memory contains a special file")
        size = path.stat().st_size
        total += size
        if size > 8 * 1024**2 or total > 64 * 1024**2 or len(result) >= 10000:
            raise ValueError("memory snapshot budget exceeded")
        result[path.relative_to(root).as_posix()] = {"sha256":sha256(path.read_bytes()).hexdigest(), "size":size}
    return result


def copy_memory(source, destination):
    expected = memory_manifest(source)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError("snapshot destination must be new")
    shutil.copytree(source, destination, symlinks=False)
    if memory_manifest(destination) != expected:
        raise RuntimeError("memory changed during snapshot")
    return expected


def changed_files(before, after):
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def extract_native(archive, destination):
    """Preserve shipped memory/SOPs. No old temp, credentials, caches or links."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    total = 0
    with tarfile.open(archive) as bundle:
        for member in bundle:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError("unsafe archive member")
            if path.parts[0] != "GenericAgent":
                continue
            if member.issym() or member.islnk():
                continue
            if not (member.isfile() or member.isdir()):
                raise ValueError("unsupported archive member")
            if any(p in ("temp", "__pycache__", ".git", ".venv") for p in path.parts):
                continue
            if path.name.startswith(".env") or path.name in ("mykey.py", "mykey.json") or path.suffix in (".pyc", ".log"):
                continue
            total += member.size
            if total > 256 * 1024**2:
                raise ValueError("native archive too large")
            bundle.extract(member, destination, filter="data")
    source = destination / "GenericAgent"
    for required in ("agentmain.py", "agent_loop.py", "ga.py", "memory/memory_management_sop.md"):
        if not (source / required).is_file():
            raise ValueError("native source or memory SOP missing: " + required)
    # The archive may omit this empty runtime directory; its mount target exists.
    (source / "temp").mkdir(exist_ok=True)
    memory_manifest(source / "memory")
    return source


class WSLJail:
    """Only runtime, native source, memory and worker support are mounted.

    No host network, host PID namespace, /mnt/c, credentials or evaluator mount.
    Requires WSL2 Ubuntu with bubblewrap; there is no unisolated fallback.
    """
    def __init__(self, distro="Ubuntu-24.04", runtime=None):
        self.distro = distro
        self.runtime = runtime or self._run(["python3", "-c",
            "from pathlib import Path; print(Path.home()/'.local/share/memorybenchmark/runtime')"]).strip()

    def _run(self, args):
        result = subprocess.run(["wsl", "-d", self.distro, "--exec", *args],
                                capture_output=True, encoding="utf-8", errors="replace", timeout=20)
        if result.returncode:
            raise IsolationError("WSL prerequisite failed: " + result.stderr[-300:])
        return result.stdout

    def path(self, path):
        return self._run(["wslpath", "-u", str(Path(path).resolve())]).strip()

    def command(self, source, memory, support, wall_seconds):
        if not 10 <= wall_seconds <= 3600:
            raise ValueError("wall budget must be 10..3600 seconds")
        for path in (source, memory, support):
            if not Path(path).is_dir() or Path(path).is_symlink():
                raise ValueError("jail mounts must be real directories")
        argv = ["timeout", "--signal=KILL", str(wall_seconds), "bwrap", "--unshare-all",
                "--die-with-parent", "--new-session", "--cap-drop", "ALL",
                "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
                "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
                "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                "--tmpfs", "/home", "--dir", "/home/agent", "--tmpfs", "/run",
                "--ro-bind", self.runtime, "/opt/ga-runtime",
                "--ro-bind", self.path(source), "/agent",
                "--bind", self.path(memory), "/agent/memory", "--tmpfs", "/agent/temp",
                "--ro-bind", self.path(support), "/runner", "--clearenv",
                "--setenv", "PATH", "/opt/ga-runtime/bin:/usr/bin:/bin",
                "--setenv", "HOME", "/home/agent", "--setenv", "LANG", "C.UTF-8",
                "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--setenv", "PYTHONUNBUFFERED", "1",
                "--setenv", "PYTHONPATH", "/runner:/agent", "--chdir", "/agent/temp",
                "/opt/ga-runtime/bin/python", "-u", "/runner/ga_worker.py"]
        return ["wsl", "-d", self.distro, "--exec", *argv]


def make_support(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("ga_worker.py", "agent_bridge.py"):
        shutil.copyfile(Path(__file__).with_name(name), destination / name)
    return destination


def encode_state(value):
    if isinstance(value, set):
        return {"$set":[encode_state(v) for v in sorted(value, key=repr)]}
    if isinstance(value, tuple):
        return {"$tuple":[encode_state(v) for v in value]}
    if isinstance(value, list): return [encode_state(v) for v in value]
    if isinstance(value, dict): return {k:encode_state(v) for k,v in value.items()}
    return value


def decode_state(value):
    if isinstance(value, list): return [decode_state(v) for v in value]
    if isinstance(value, dict):
        if set(value) == {"$set"}: return set(decode_state(v) for v in value["$set"])
        if set(value) == {"$tuple"}: return tuple(decode_state(v) for v in value["$tuple"])
        return {k:decode_state(v) for k,v in value.items()}
    return value


def state_digest(state):
    return sha256(json.dumps(encode_state(state), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
