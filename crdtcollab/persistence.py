"""Append-only JSONL operation log with fsync and deterministic replay."""
import json, os
from pathlib import Path
from .sequence import Operation, SequenceCRDT

class OperationLog:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
    def append(self,op):
        with self.path.open("a",encoding="utf-8") as f:
            f.write(json.dumps(op.to_dict(),sort_keys=True,separators=(",",":"))+"\n")
            f.flush(); os.fsync(f.fileno())
    def append_all(self,ops):
        for op in ops: self.append(op)
    def replay(self,site_id):
        replica=SequenceCRDT(site_id)
        if not self.path.exists(): return replica
        lines=self.path.read_bytes().splitlines(keepends=True)
        for i,line in enumerate(lines):
            if not line.endswith(b"\n") and i==len(lines)-1: break
            try: replica.apply(Operation.from_dict(json.loads(line.decode("utf-8"))))
            except Exception as e: raise ValueError(f"invalid operation log line {i+1}: {e}") from e
        return replica
