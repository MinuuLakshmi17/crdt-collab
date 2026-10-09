"""RGA-inspired sequence CRDT with idempotent operations and tombstones."""
from dataclasses import dataclass
from typing import Any, Iterable
import json

@dataclass(frozen=True, order=True, slots=True)
class OpId:
    site_id: str
    counter: int
    def __post_init__(self):
        if not self.site_id or self.counter < 1: raise ValueError("invalid operation ID")
    def encode(self): return f"{self.site_id}:{self.counter}"
    @classmethod
    def decode(cls, value):
        site, count = value.rsplit(":", 1)
        return cls(site, int(count))

ROOT = OpId("_root", 1)

@dataclass(frozen=True, slots=True)
class Operation:
    kind: str
    op_id: OpId
    parent_id: OpId | None = None
    target_id: OpId | None = None
    value: str | None = None
    def __post_init__(self):
        if self.kind not in ("insert", "delete"): raise ValueError("unknown operation")
        if self.kind == "insert" and (self.parent_id is None or self.value is None or len(self.value) != 1):
            raise ValueError("insert requires parent and one code point")
        if self.kind == "delete" and self.target_id is None: raise ValueError("delete requires target")
    def to_dict(self):
        return {"kind":self.kind,"op_id":self.op_id.encode(),"parent_id":self.parent_id.encode() if self.parent_id else None,
                "target_id":self.target_id.encode() if self.target_id else None,"value":self.value}
    @classmethod
    def from_dict(cls, d):
        return cls(d["kind"], OpId.decode(d["op_id"]), OpId.decode(d["parent_id"]) if d.get("parent_id") else None,
                   OpId.decode(d["target_id"]) if d.get("target_id") else None, d.get("value"))

@dataclass
class Element:
    op_id: OpId
    parent_id: OpId
    value: str
    deleted: bool = False

class SequenceCRDT:
    def __init__(self, site_id: str):
        if not site_id or site_id == "_root": raise ValueError("reserved/empty site ID")
        self.site_id, self._counter = site_id, 0
        self._elements: dict[OpId, Element] = {}
        self._children: dict[OpId, set[OpId]] = {ROOT:set()}
        self._ops: dict[OpId, Operation] = {}
        self._pending_inserts: dict[OpId, Operation] = {}
        self._pending_deletes: set[OpId] = set()
        self._clock: dict[str,int] = {}
    @property
    def vector_clock(self): return dict(self._clock)
    @property
    def operations(self): return sorted(self._ops.values(), key=lambda x:x.op_id)
    def _new_id(self):
        self._counter += 1; self._clock[self.site_id] = self._counter
        return OpId(self.site_id,self._counter)
    def insert(self,index:int,text:str):
        visible=self._visible()
        if not 0 <= index <= len(visible): raise IndexError("insert index out of range")
        parent=ROOT if index==0 else visible[index-1].op_id
        result=[]
        for ch in text:
            op=Operation("insert",self._new_id(),parent_id=parent,value=ch)
            self.apply(op); result.append(op); parent=op.op_id
        return result
    def delete(self,index:int,count:int=1):
        visible=self._visible()
        if count < 0 or index < 0 or index+count > len(visible): raise IndexError("delete range out of bounds")
        result=[]
        for el in visible[index:index+count]:
            op=Operation("delete",self._new_id(),target_id=el.op_id)
            self.apply(op); result.append(op)
        return result
    def apply_all(self,ops:Iterable[Operation]):
        for op in ops: self.apply(op)
    def apply(self,op:Operation):
        old=self._ops.get(op.op_id)
        if old is not None:
            if old != op: raise ValueError(f"conflicting payload for {op.op_id.encode()}")
            return False
        self._ops[op.op_id]=op
        self._clock[op.op_id.site_id]=max(self._clock.get(op.op_id.site_id,0),op.op_id.counter)
        if op.op_id.site_id==self.site_id: self._counter=max(self._counter,op.op_id.counter)
        if op.kind=="delete":
            target=self._elements.get(op.target_id)
            if target: target.deleted=True
            else: self._pending_deletes.add(op.target_id)
        else:
            if op.parent_id != ROOT and op.parent_id not in self._elements:
                self._pending_inserts[op.op_id]=op
            else: self._install(op)
            self._drain()
        return True
    def _install(self,op):
        if op.op_id in self._elements: return
        el=Element(op.op_id,op.parent_id,op.value,op.op_id in self._pending_deletes)
        self._pending_deletes.discard(op.op_id)
        self._elements[op.op_id]=el
        self._children.setdefault(op.parent_id,set()).add(op.op_id)
        self._children.setdefault(op.op_id,set())
    def _drain(self):
        progress=True
        while progress:
            progress=False
            for oid,op in sorted(list(self._pending_inserts.items())):
                if op.parent_id==ROOT or op.parent_id in self._elements:
                    self._install(op); del self._pending_inserts[oid]; progress=True
    def _ordered(self):
        out = []
        # Iterative depth-first walk. Sequential inserts chain each element
        # to the previous one, so a long document is a deep linked list and
        # a recursive walk overflows the stack past ~1000 elements.
        # Children are pushed in reverse-sorted order so they pop smallest-first,
        # reproducing the recursive pre-order exactly.
        stack = sorted(self._children.get(ROOT, set()), reverse=True)
        while stack:
            oid = stack.pop()
            out.append(self._elements[oid])
            stack.extend(sorted(self._children.get(oid, set()), reverse=True))
        return out
    def _visible(self): return [el for el in self._ordered() if not el.deleted]
    @property
    def text(self): return "".join(el.value for el in self._visible())
    def __len__(self): return len(self._visible())
    def merge(self,other): self.apply_all(other.operations)
    def export_state(self):
        return {"format_version":1,"site_id":self.site_id,"operations":[o.to_dict() for o in self.operations]}
    @classmethod
    def from_state(cls,state,site_id=None):
        if state.get("format_version")!=1: raise ValueError("unsupported state version")
        r=cls(site_id or state["site_id"]); r.apply_all(Operation.from_dict(o) for o in state["operations"]); return r
    def to_json(self): return json.dumps(self.export_state(),sort_keys=True,separators=(",",":"))
