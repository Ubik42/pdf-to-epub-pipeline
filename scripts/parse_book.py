#!/usr/bin/env python3
"""Parse a scanned PDF in restartable page ranges with MinerU."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--pages", type=int, required=True)
    parser.add_argument("--chunk-size", type=int, default=32)
    parser.add_argument("--tier", default="standard")
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    current_hash = sha256(args.pdf)
    if args.expected_sha256 and current_hash.lower() != args.expected_sha256.lower():
        raise ValueError("Source PDF SHA-256 changed; refusing to mix page segments")

    mineru = Path(sys.executable).with_name("mineru-kit.exe")
    segments = []
    for first in range(1, args.pages + 1, args.chunk_size):
        last = min(first + args.chunk_size - 1, args.pages)
        name = f"pages-{first:04d}-{last:04d}"
        md = args.work_dir / f"{name}.md"
        info = args.work_dir / f"{name}.json"
        log = args.work_dir / f"{name}.log"
        segments.append(md)

        if md.is_file() and md.stat().st_size > 500 and info.is_file():
            metadata = json.loads(info.read_text(encoding="utf-8"))
            if metadata.get("source_sha256") == current_hash and metadata.get("pages") == [first, last]:
                print(f"SKIP {name}: complete", flush=True)
                continue

        command = [
            str(mineru), "parse", str(args.pdf), "--output", str(md),
            "--pages", f"{first}-{last}", "--tier", args.tier,
            "--ocr-mode", "ocr", "--verbose",
        ]
        for attempt in range(1, args.retries + 2):
            started = time.time()
            print(f"START {name} attempt {attempt}", flush=True)
            with log.open("a", encoding="utf-8") as stream:
                stream.write(f"\n=== attempt {attempt} at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                stream.flush()
                result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
            if result.returncode == 0 and md.is_file() and md.stat().st_size > 500:
                metadata = {
                    "source_sha256": current_hash,
                    "pages": [first, last],
                    "tier": args.tier,
                    "seconds": round(time.time() - started, 1),
                    "markdown_bytes": md.stat().st_size,
                }
                info.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"DONE {name} in {metadata['seconds']}s", flush=True)
                break
            print(f"FAILED {name} exit={result.returncode}", flush=True)
        else:
            print(f"STOP: {name} failed after retries", flush=True)
            return 1

    combined = args.work_dir.parent / "运筹学（第5版）.md"
    combined.write_text(
        "\n\n".join(part.read_text(encoding="utf-8").strip() for part in segments) + "\n",
        encoding="utf-8",
    )
    print(f"COMBINED {combined} ({combined.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
