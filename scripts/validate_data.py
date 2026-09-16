"""Validate a HomeNHealthy release without making network requests."""

from pathlib import Path
import argparse
import json
import sys

from update_data import validate_dataset


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-publishable", action="store_true")
    args = parser.parse_args()
    payload = json.loads((ROOT / "data/healthy-home-index.json").read_text())
    errors, warnings = validate_dataset(payload, require_publishable=args.require_publishable)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        sys.exit(1)
    print(f"Data quality gate passed for {len(payload['cities'])} city records.")


if __name__ == "__main__":
    main()
