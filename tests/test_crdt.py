import random, json
from crdtcollab import SequenceCRDT, OperationLog
from crdtcollab.sequence import Operation
import pytest

def test_insert_delete():
    d=SequenceCRDT("alice"); d.insert(0,"hello"); d.insert(5,"!"); d.delete(1,3)
    assert d.text=="ho!"
def test_concurrent_insert_converges():
    a,b=SequenceCRDT("alice"),SequenceCRDT("bob")
    a.insert(0,"A"); b.insert(0,"B"); a.merge(b); b.merge(a)
    assert a.text==b.text and len(a.text)==2
def test_random_delivery_order_converges():
    rng=random.Random(20261009); base=SequenceCRDT("base"); base.insert(0,"root")
    a=SequenceCRDT.from_state(base.export_state(),"alice")
    b=SequenceCRDT.from_state(base.export_state(),"bob")
    c=SequenceCRDT.from_state(base.export_state(),"carol")
    ops=a.insert(2,"XYZ")+b.insert(1,"12")+c.insert(4,"!?")+b.delete(0)
    texts=[]
    for site in ("r1","r2","r3","r4"):
        replica=SequenceCRDT(site); shuffled=list(ops); rng.shuffle(shuffled); replica.apply_all(shuffled); texts.append(replica.text)
    assert len(set(texts))==1
def test_parent_and_delete_out_of_order():
    src=SequenceCRDT("src"); ins=src.insert(0,"abc"); delete=src.delete(1)[0]
    r=SequenceCRDT("r"); r.apply(delete); r.apply(ins[2]); r.apply(ins[0]); r.apply(ins[1])
    assert r.text=="ac"
def test_idempotency_and_conflict():
    a=SequenceCRDT("a"); op=a.insert(0,"x")[0]; b=SequenceCRDT("b")
    assert b.apply(op) is True and b.apply(op) is False
    bad=Operation("insert",op.op_id,parent_id=op.parent_id,value="z")
    with pytest.raises(ValueError,match="conflicting"): b.apply(bad)
def test_persist_and_replay(tmp_path):
    path=tmp_path/"ops.jsonl"; d=SequenceCRDT("writer"); inserts=d.insert(0,"durable"); deletes=d.delete(1)
    log=OperationLog(path); log.append_all(inserts+deletes); restored=log.replay("restored")
    assert restored.text==d.text=="drable"
def test_ignores_partial_final_line(tmp_path):
    path=tmp_path/"ops.jsonl"; d=SequenceCRDT("a"); op=d.insert(0,"x")[0]
    path.write_text(json.dumps(op.to_dict())+"\n"+'{"kind":',encoding="utf-8")
    assert OperationLog(path).replay("replay").text=="x"
def test_state_round_trip():
    d=SequenceCRDT("alice"); d.insert(0,"CRDT"); d.delete(2)
    r=SequenceCRDT.from_state(d.export_state(),"restored")
    assert r.text==d.text and r.vector_clock["alice"]==5
