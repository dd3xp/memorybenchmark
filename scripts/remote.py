"""Run a local PowerShell file on the configured Squishy SSH host."""

import argparse
import base64
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("timeout", nargs="?", type=int, default=120)
    args = parser.parse_args()
    source = args.script.read_text(encoding="utf-8-sig")
    prefix = (
        "$ProgressPreference='SilentlyContinue'; "
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8\n"
    )
    encoded = base64.b64encode((prefix + source).encode("utf-16le")).decode()
    command = [
        "ssh",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "Squishy",
        "powershell -NoProfile -EncodedCommand " + encoded,
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        # Avoid exposing the encoded script in an exception traceback. A read
        # timeout also says nothing about a remote experiment's process state.
        print(f"SSH observation timed out after {args.timeout}s.", file=sys.stderr)
        return 124
    sys.stdout.write(result.stdout.decode("utf-8", errors="replace"))
    if result.returncode:
        sys.stderr.write(result.stderr.decode("utf-8", errors="replace"))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
