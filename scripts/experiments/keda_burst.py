"""KEDA 0→N→0 burst experiment.

Floods upload-api with the corpus a few times in quick succession to back the
Redis (RQ) queue up, then samples the embedding-worker replica count over
~10 minutes via the kubectl proxy or via direct API access. Outputs:

  out/keda_burst/timeline.csv     — (t, queue_depth, replicas)
  out/keda_burst/summary.md       — markdown summary
  out/keda_burst/replicas.png     — replica-count plot if matplotlib is on path

Intended to run from CI (`gh workflow run experiment.yml -f experiment=keda-burst`)
or locally via uv with `kubectl` configured.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import pathlib
import subprocess
import sys
import time

import httpx

UPLOAD_API_URL = os.environ.get("UPLOAD_API_URL", "https://rag-ingest.dev.michaelalinks.com")
TENANT_ID = os.environ.get("INGEST_TENANT_ID", "keda-burst")
REPLAYS = int(os.environ.get("BURST_REPLAYS", "5"))
SAMPLE_SECONDS = int(os.environ.get("BURST_SAMPLE_SECONDS", "600"))
SAMPLE_INTERVAL = int(os.environ.get("BURST_SAMPLE_INTERVAL", "10"))


async def flood() -> int:
    root = pathlib.Path(__file__).resolve().parents[2]
    docs = sorted((root / "corpus").rglob("*.md"))
    if not docs:
        print("no corpus", file=sys.stderr)
        return 1

    async with httpx.AsyncClient() as client:
        for replay in range(REPLAYS):
            tasks = [
                client.post(
                    f"{UPLOAD_API_URL}/documents",
                    json={
                        "content": p.read_text(),
                        "source_doc": f"{p.name}#r{replay}",
                        "tenant_id": TENANT_ID,
                    },
                    timeout=60,
                )
                for p in docs
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            failures = [r for r in results if isinstance(r, Exception)]
            print(f"replay {replay}: queued={len(results) - len(failures)} failed={len(failures)}")
    return 0


def sample_replicas() -> int:
    out = subprocess.run(
        ["kubectl", "get", "deployment", "embedding-worker", "-n", "ingestion", "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    spec = json.loads(out.stdout)
    return int(spec.get("status", {}).get("replicas", 0))


def main() -> int:
    out_dir = pathlib.Path(__file__).resolve().parents[2] / "out/keda_burst"
    out_dir.mkdir(parents=True, exist_ok=True)

    asyncio.run(flood())

    csv_path = out_dir / "timeline.csv"
    samples: list[tuple[float, int]] = []
    with csv_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["seconds_since_flood", "embedding_worker_replicas"])
        start = time.monotonic()
        end = start + SAMPLE_SECONDS
        while time.monotonic() < end:
            t = time.monotonic() - start
            replicas = sample_replicas()
            samples.append((t, replicas))
            writer.writerow([f"{t:.1f}", replicas])
            fh.flush()
            time.sleep(SAMPLE_INTERVAL)

    peak = max(r for _, r in samples) if samples else 0
    settled_zero = samples[-1][1] == 0 if samples else False

    (out_dir / "summary.md").write_text(
        f"""# KEDA 0 → N → 0 burst

- Documents queued per replay: {len(list((pathlib.Path(__file__).resolve().parents[2] / 'corpus').rglob('*.md')))}
- Replays: {REPLAYS}
- Sample window: {SAMPLE_SECONDS}s @ {SAMPLE_INTERVAL}s interval
- **Peak embedding-worker replicas: {peak}**
- **Settled back to zero: {'yes' if settled_zero else 'no'}**

See timeline.csv for the full trajectory.
"""
    )

    try:
        import matplotlib.pyplot as plt

        ts, replicas = zip(*samples)
        plt.figure(figsize=(8, 3))
        plt.plot(ts, replicas)
        plt.xlabel("seconds since flood")
        plt.ylabel("embedding-worker replicas")
        plt.title("KEDA 0 → N → 0 on Redis queue depth")
        plt.tight_layout()
        plt.savefig(out_dir / "replicas.png", dpi=150)
    except Exception:
        pass

    print(f"peak={peak} settled_zero={settled_zero}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
