"""Regenerate the golden 'kern' byte files from the current package output.

Run this ONLY when a kern-output change is intentional (and reviewed):

    python tests/regen_golden.py

It writes tests/golden/<case>.kern.bin for every case in test_golden.CASES.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from test_golden import CASES, GOLDEN_DIR, produce_kern_bytes  # noqa: E402


def main():
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    for name in CASES:
        data = produce_kern_bytes(name)
        with open(os.path.join(GOLDEN_DIR, name + ".kern.bin"), "wb") as fh:
            fh.write(data)
        print("wrote", name, f"({len(data)} bytes)")


if __name__ == "__main__":
    main()
