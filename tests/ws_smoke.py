"""Smoke-test для WebSocket /api/ws: локально и через ingress (wss)."""
import asyncio
import json
import sys
import time

import requests
import websockets

LOCAL_HTTP = "http://localhost:8001"
EXT = "https://trainbrain-2.preview.emergentagent.com"


def register():
    email = f"wstest+{int(time.time())}@example.com"
    r = requests.post(f"{LOCAL_HTTP}/api/auth/register",
                      json={"email": email, "password": "password123", "name": "WS Tester"},
                      timeout=20)
    r.raise_for_status()
    data = r.json()
    return data["token"], data["user"]["telegram_id"]


async def test_ws(url, token, label):
    full = f"{url}?token={token}"
    try:
        async with websockets.connect(full, open_timeout=15, ping_interval=None) as ws:
            first = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(first)
            print(f"[{label}] connected msg: {msg.get('type')} payload={msg.get('payload')}")
            await ws.send(json.dumps({"type": "ping"}))
            pong = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f"[{label}] ping->{json.loads(pong).get('type')}")
            return True
    except Exception as e:
        print(f"[{label}] FAILED: {type(e).__name__}: {e}")
        return False


async def test_unauth(url, label):
    try:
        async with websockets.connect(f"{url}?token=BADTOKEN", open_timeout=15, ping_interval=None) as ws:
            await asyncio.wait_for(ws.recv(), timeout=8)
            print(f"[{label}] UNAUTH: unexpectedly received message (should have closed)")
            return False
    except Exception as e:
        print(f"[{label}] UNAUTH correctly rejected: {type(e).__name__}")
        return True


async def main():
    token, tgid = register()
    print(f"Registered telegram_id={tgid}")
    local_ws = "ws://localhost:8001/api/ws"
    ext_ws = EXT.replace("https://", "wss://") + "/api/ws"
    r1 = await test_ws(local_ws, token, "LOCAL")
    r2 = await test_ws(ext_ws, token, "INGRESS")
    r3 = await test_unauth(local_ws, "LOCAL")
    print("\nRESULT:", {"local": r1, "ingress": r2, "unauth_reject": r3})
    sys.exit(0 if (r1 and r3) else 1)


asyncio.run(main())
