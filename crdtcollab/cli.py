import argparse, asyncio, json
from .sequence import SequenceCRDT
from .persistence import OperationLog
from .sync import run_server
def main():
    p=argparse.ArgumentParser(description="CRDT text collaboration demo"); sub=p.add_subparsers(dest="cmd",required=True)
    e=sub.add_parser("edit"); e.add_argument("--site",required=True); e.add_argument("--text",required=True); e.add_argument("--log",default="state/ops.jsonl")
    r=sub.add_parser("replay"); r.add_argument("--site",default="restored"); r.add_argument("--log",default="state/ops.jsonl")
    s=sub.add_parser("serve"); s.add_argument("--host",default="127.0.0.1"); s.add_argument("--port",type=int,default=8765)
    a=p.parse_args()
    if a.cmd=="edit":
        log=OperationLog(a.log); doc=log.replay(a.site); ops=doc.insert(len(doc),a.text); log.append_all(ops)
        print(json.dumps({"text":doc.text,"operations_written":len(ops)}))
    elif a.cmd=="replay":
        doc=OperationLog(a.log).replay(a.site); print(json.dumps({"text":doc.text,"vector_clock":doc.vector_clock},indent=2))
    else: asyncio.run(run_server(a.host,a.port))
if __name__=="__main__": main()
