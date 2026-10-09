# crdt-collab

<p align="justify">
An operation-based sequence CRDT for collaborative text editing, inspired by the Replicated Growable Array (RGA) of Roh et al. Replicas apply the same set of insert and delete operations in any order — including duplicates and arrivals before their causal parents — and deterministically converge to the same document without coordination, locking, or a central server. The implementation includes an append-only operation log with crash-safe replay, vector-clock tracking, and an optional WebSocket relay for live sessions.
</p>

## Background

<p align="justify">
Real-time collaborative editors (Google Docs, Figma) face a fundamental problem: when two users type at the same position simultaneously, with network delay between them, how do all replicas agree on the final document? Operational Transformation (OT) solves this with a central server that rewrites operations against each other. Conflict-free Replicated Data Types (CRDTs) take a different path: they design the operations so that <em>every pair of operations commutes</em> — applying them in any order yields the same state. No server, no locking, no consensus round trips. This project implements the operation-based (op-based) variant for an ordered sequence of characters.
</p>

<p align="justify">
The core idea, following RGA: every inserted character gets a globally unique operation ID <code>(site_id, counter)</code> and records the ID of its <em>parent</em> — the character it was inserted after. The document is the depth-first traversal of this parent/children tree, with siblings ordered by operation ID. Because parent pointers are immutable and sibling order is a total order on unique IDs, every replica that has seen the same operations renders the same tree walk, regardless of arrival order. Deletes do not remove nodes; they mark them as <em>tombstones</em>, because a concurrent insert elsewhere may still reference the deleted node as its parent. Removing it would orphan that insert on some replicas and break convergence.
</p>

## Why convergence holds

<p align="justify">
Convergence reduces to a commutativity argument. The replica state is a function of the <em>set</em> of applied operations, never of their arrival sequence: inserting an operation only adds a node to the tree (or buffers it until its parent arrives), and deleting only flips a tombstone flag. Both are idempotent — reapplying an operation is detected via the operation-ID registry and ignored, while a reused ID with a different payload is rejected as a conflict rather than silently corrupting state. Since every operation commutes with every other and application is idempotent, any two replicas that have received the same operation set hold identical trees and render identical text. The test suite verifies this empirically, including a randomized trial where operations are shuffled and duplicated before delivery.
</p>

## Design

<p align="justify">
Operations are small validated dataclasses: <code>insert</code> carries an operation ID, a parent ID, and exactly one code point; <code>delete</code> carries an operation ID and a target ID. The engine maintains the element table, the children index, the operation registry, and two buffers — one for inserts whose parent has not arrived yet, one for deletes whose target has not arrived yet. Both buffers drain deterministically as missing operations arrive, which is what makes the engine robust to arbitrary network reordering without any causal-delivery layer. Each replica also tracks a vector clock (per-site counters), which supports reasoning about happened-before relationships even though delivery does not depend on it.
</p>

<p align="justify">
Persistence is an append-only JSONL operation log: every operation is serialized, flushed, and <code>fsync</code>'d before acknowledgement, and replay tolerates a torn final line (the standard crash-during-write case) by ignoring the incomplete record. The optional WebSocket relay is deliberately dumb — it broadcasts operation batches between connected peers and owns no document state, which keeps the convergence guarantee entirely in the CRDT layer where it can be tested without a network.
</p>

## Complexity

<p align="justify">
Local insert is O(n) in the document size because it re-renders the visible sequence to resolve the index into a parent pointer; applying a remote operation is O(1) amortized (hash-table install plus bounded buffer draining); merging two replicas is O(m log m) in the number of exchanged operations due to ID sorting; rendering the document is O(n). The honest cost of this design is the O(n) local insert — production editors index the sequence (e.g., a balanced tree over the RGA) to make it logarithmic. For an educational implementation the linear scan keeps the ordering invariant obvious, and the benchmark below quantifies exactly what it costs.
</p>

## Benchmark

<p align="justify">
Measured with <code>scripts/bench.py</code> on a 2-vCPU cloud VM (best of 3 runs):
</p>

| ops | insert ms/op | apply ms/op | merge ms | render ms |
|---|---|---|---|---|
| 100 | 0.095 | 0.004 | 1.0 | 0.085 |
| 500 | 0.398 | 0.004 | 5.0 | 0.397 |
| 2,000 | 1.592 | 0.004 | 21.7 | 1.679 |
| 5,000 | 3.877 | 0.004 | 54.0 | 3.999 |

<p align="justify">
Remote apply holds steady at 4 microseconds per operation — roughly 250,000 ops/sec — regardless of document size, which is the number that matters for sync-heavy workloads. Insert and render grow linearly, as the complexity analysis predicts. Merge cost is linear in the exchanged operation count.
</p>

<p align="justify">
One measurement shaped the implementation: the first benchmark run crashed with <code>RecursionError</code> at 2,000 operations, because sequential inserts chain each character to the previous one and the original recursive tree walk overflowed the call stack. The traversal is now iterative and provably order-identical to the recursive version (differentially tested across randomized operation histories). A collaborative editor that cannot hold a 2,000-character document is not a serious artifact; this one now handles 5,000 without blinking.
</p>

## Demos

<p align="justify">
<code>examples/demo.py</code> shows the canonical case: Alice types "Hello" and Bob types "World" at the same position concurrently. Both converge to "HelloWorld" — concurrent inserts at one position are ordered by operation ID rather than interleaved, which is correct RGA semantics and the behavior Figma-style applications depend on for deterministic rendering.
</p>

<p align="justify">
<code>examples/partition.py</code> simulates a network partition: the replicas edit independently and visibly diverge (<code>'Hello brave new'</code> vs <code>'Hoi'</code>), then the partition heals, operation sets are exchanged, and both converge to <code>'Ho brave newi'</code> — Bob's delete of "ell" deterministically composes with Alice's insert, with no manual conflict resolution.
</p>

## Verification

<p align="justify">
The test suite (<code>pytest tests/</code>) covers insert/delete, concurrent-insert convergence, randomized delivery order across four replicas, missing-parent buffering, delete-before-insert, idempotency, conflicting operation-ID rejection, operation-log persistence and replay, torn-log recovery, and state round-trips — all with deterministic seeds. The randomized convergence test additionally shuffles and duplicates operations before delivery. These tests are evidence, not proof; the convergence argument above is the reason to believe the property holds beyond the tested cases.
</p>

## Limitations

<p align="justify">
Stated plainly: this is a single-document, code-point-granularity engine, not a production collaboration service. There is no tombstone compaction, so history grows indefinitely. The WebSocket relay is best-effort broadcast with no authentication, persistence, backpressure, or document isolation. Vector clocks are tracked but not used to gate delivery. Rich text, undo/redo, and presence are out of scope. The operation log assumes a single writer per file.
</p>

## Project structure

```text
crdt-collab/
├── crdtcollab/
│   ├── sequence.py      # RGA sequence CRDT: ops, engine, convergence logic
│   ├── persistence.py   # fsync'd JSONL operation log with torn-write recovery
│   ├── sync.py          # optional WebSocket broadcast relay (no document state)
│   └── cli.py           # edit / replay / serve commands
├── examples/
│   ├── demo.py          # concurrent insert convergence
│   └── partition.py     # partition, divergence, and healing
├── scripts/
│   └── bench.py         # insert / apply / merge / render benchmarks
└── tests/
    └── test_crdt.py     # convergence, idempotency, persistence tests
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python examples/demo.py
python examples/partition.py
python scripts/bench.py
```

Persist and replay a document:

```bash
crdt-collab edit --site alice --text "Hello" --log state/ops.jsonl
crdt-collab edit --site alice --text " world" --log state/ops.jsonl
crdt-collab replay --site recovered --log state/ops.jsonl
```

Live relay (requires the `websocket` extra):

```bash
pip install -e ".[dev,websocket]"
crdt-collab serve --host 127.0.0.1 --port 8765
```

## License

MIT — see [LICENSE](LICENSE).
