"""Verify that the model paths in config.yaml exist. Run: python check_models.py"""
import os
from config import _raw

all_ok = True
for role, c in _raw["models"].items():
    if role == "embedding":
        continue
    path = c.get("path", "")
    exists = os.path.exists(path)
    print(f"  [{'OK' if exists else 'MISSING'}] {role}: {path}")
    all_ok = all_ok and exists

raise SystemExit(0 if all_ok else 1)
