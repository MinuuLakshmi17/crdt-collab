"""Network partition and healing: two replicas edit the same document while
disconnected, visibly diverge, then converge once the partition heals.

Usage: python examples/partition.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from crdtcollab import SequenceCRDT

# Both replicas start from the same document.
alice = SequenceCRDT("alice")
alice.insert(0, "Hello")
bob = SequenceCRDT.from_state(alice.export_state(), "bob")

print(f"before partition: alice={alice.text!r} bob={bob.text!r}")

# --- partition: no operation exchange ---
alice.insert(5, " brave new")          # "Hello brave new"
bob.delete(1, 3)                       # "Ho"
bob.insert(2, "i")                     # "Hoi"

print(f"during partition: alice={alice.text!r} bob={bob.text!r}")
assert alice.text != bob.text, "replicas should have diverged"

# --- partition heals: exchange operation sets both ways ---
alice.merge(bob)
bob.merge(alice)

print(f"after healing:    alice={alice.text!r} bob={bob.text!r}")
assert alice.text == bob.text
print("Converged:", True)
