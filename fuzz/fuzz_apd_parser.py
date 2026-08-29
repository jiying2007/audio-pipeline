#!/usr/bin/env python3
from __future__ import annotations
import os, random, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import apdump

def one(data: bytes) -> None:
    try:
        h = apdump.read_header(data)
        list(apdump.iter_records(h, data))
    except (ValueError, struct.error, OverflowError, UnicodeError):
        pass

def main() -> int:
    random.seed(0xA12D)
    for _ in range(5000):
        n = random.randint(0, 4096)
        one(os.urandom(n))
    # Structured mutations around a minimally sized header exercise stride/count overflow paths.
    base = bytearray(apdump.HEADER.size)
    for _ in range(2000):
        data = bytearray(base)
        for _ in range(random.randint(1, 12)):
            if data:
                data[random.randrange(len(data))] = random.randrange(256)
        one(bytes(data))
    print('APD malformed-input fuzz: OK')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
