import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from crdtcollab import SequenceCRDT
alice,bob=SequenceCRDT("alice"),SequenceCRDT("bob")
alice.insert(0,"Hello"); bob.insert(0,"World")
alice.merge(bob); bob.merge(alice)
print("Alice:",alice.text); print("Bob:",bob.text); print("Converged:",alice.text==bob.text)
