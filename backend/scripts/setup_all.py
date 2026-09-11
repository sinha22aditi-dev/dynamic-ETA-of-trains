#!/usr/bin/env python3
"""
setup_all.py — One-shot setup script for DynamicRail backend.

Steps:
1. Create PostgreSQL DB and user
2. Run Alembic migrations
3. Seed reference data (stations, trains, routes)
4. Seed replay source (30k sequential rows)

Run from backend/ directory:
  python scripts/setup_all.py

Environment:
  Set DATABASE_URL in .env or pass via environment.
"""

import subprocess
import sys
import os

def run(cmd, cwd=None, check=True):
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=False)
    if check and result.returncode != 0:
        print(f"ERROR: command failed with code {result.returncode}")
        sys.exit(result.returncode)
    return result


def main():
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)
    print(f"Working directory: {backend_dir}")

    print("\n=== Step 1: Run Alembic migrations ===")
    run("alembic upgrade head")

    print("\n=== Step 2: Seed reference data (stations, trains, routes) ===")
    run(f"{sys.executable} seed/seed_reference_data.py")

    print("\n=== Step 3: Seed replay source (~30k rows) ===")
    run(f"{sys.executable} seed/seed_replay_source.py")

    print("\n=== Setup complete! ===")
    print("Start the backend with:")
    print("  uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload")


if __name__ == "__main__":
    main()
