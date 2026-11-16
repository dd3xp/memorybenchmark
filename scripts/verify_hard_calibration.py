"""Verify one already downloaded, sealed native calibration archive once."""

import argparse
import json
from pathlib import Path

from memorybenchmark.experiments.verification import verify_download


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, required=True)
    args = parser.parse_args()
    value = verify_download(args.folder)
    print(json.dumps(value, ensure_ascii=True))


if __name__ == "__main__":
    main()
