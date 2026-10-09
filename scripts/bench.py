"""Benchmarks: local op throughput and merge cost vs document size.

Usage: python scripts/bench.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crdtcollab import SequenceCRDT


def timeit(fn, rounds=3):
    best = float("inf")
    for _ in range(rounds):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def main():
    print(f"{'ops':>8} {'insert_ms/op':>13} {'apply_ms/op':>12} {'merge_ms':>9} {'render_ms':>10}")
    for n in (100, 500, 2000, 5000):
        # Local insert throughput (each insert also renders via _visible).
        doc = SequenceCRDT("bench")

        def do_inserts():
            d = SequenceCRDT("bench")
            for i in range(n):
                d.insert(i % (len(d) + 1), "x")

        insert_s = timeit(do_inserts) / n * 1000

        # Remote apply throughput: pre-generate ops, then apply to a fresh replica.
        src = SequenceCRDT("src")
        ops = src.insert(0, "x" * n)

        def do_apply():
            r = SequenceCRDT("r")
            r.apply_all(ops)

        apply_s = timeit(do_apply) / n * 1000

        # Merge cost: two divergent replicas exchange full op sets.
        a, b = SequenceCRDT("a"), SequenceCRDT("b")
        a.insert(0, "a" * (n // 2))
        b.insert(0, "b" * (n // 2))

        def do_merge():
            x, y = SequenceCRDT("x"), SequenceCRDT("y")
            x.apply_all(a.operations)
            y.apply_all(b.operations)
            x.merge(y)
            y.merge(x)
            assert x.text == y.text

        merge_s = timeit(do_merge) * 1000

        # Text render cost on a converged document.
        c = SequenceCRDT("c")
        c.apply_all(ops)
        render_s = timeit(lambda: c.text) * 1000

        print(f"{n:>8} {insert_s:>13.3f} {apply_s:>12.3f} {merge_s:>9.1f} {render_s:>10.3f}")


if __name__ == "__main__":
    main()
