"""Optional WebSocket broadcast relay. Install the websocket extra first."""
import asyncio, json
async def run_server(host="127.0.0.1",port=8765):
    try:
        from websockets.asyncio.server import serve
    except ImportError as e:
        raise RuntimeError("Install WebSocket support: pip install -e '.[websocket]'") from e
    peers=set()
    async def handler(ws):
        peers.add(ws)
        try:
            async for message in ws:
                data=json.loads(message)
                if data.get("type") not in ("ops","snapshot"):
                    await ws.send(json.dumps({"type":"error","message":"expected ops or snapshot"})); continue
                for peer in tuple(peers):
                    if peer is ws: continue
                    try: await peer.send(json.dumps(data,separators=(",",":")))
                    except Exception: peers.discard(peer)
        finally: peers.discard(ws)
    async with serve(handler,host,port):
        print(f"CRDT relay listening on ws://{host}:{port}")
        await asyncio.Future()
