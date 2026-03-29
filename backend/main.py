import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from producer import producer
from consumer import consumer

# ── Lifespan ───────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.queue      = asyncio.Queue()
    app.state.clients    = set()
    # Ring buffer — last 20 ads for polling clients
    app.state.recent_ads = []

    producer_task = asyncio.create_task(producer(app.state.queue))
    consumer_task = asyncio.create_task(
        consumer(app.state.queue, app.state.clients, app.state.recent_ads)
    )

    print("✅ Backend started")
    print("🌐 WebSocket: /ws  |  Polling: /ads")
    yield

    print("🛑 Shutting down...")
    producer_task.cancel()
    consumer_task.cancel()
    try:
        await asyncio.gather(producer_task, consumer_task, return_exceptions=True)
    except Exception:
        pass

# ── App ────────────────────────────────────────────────────────
app = FastAPI(title="EchoAd - Real-Time Ad Bidding Simulator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://echoad.vercel.app",        # ✅ production frontend
        "http://localhost:5173",             # ✅ local dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── HTTP Routes ────────────────────────────────────────────────
@app.get("/")
async def root(request: Request):
    return {
        "status":    "running",
        "message":   "EchoAd Backend is live",
        "websocket": "/ws",
        "polling":   "/ads",
        "clients":   len(request.app.state.clients),
        "queue":     request.app.state.queue.qsize(),
    }

@app.get("/health")
async def health(request: Request):
    return {
        "status":            "ok",
        "connected_clients": len(request.app.state.clients),
        "queue_size":        request.app.state.queue.qsize(),
    }

@app.get("/stats")
async def stats(request: Request):
    return {
        "connected_clients": len(request.app.state.clients),
        "queue_size":        request.app.state.queue.qsize(),
    }

# Polling endpoint — returns last N ads
@app.get("/ads")
async def get_ads(request: Request, limit: int = 5):
    recent = request.app.state.recent_ads
    return {
        "ads":   recent[-limit:],
        "count": len(recent),
        "mode":  "polling",
    }

# ── WebSocket ──────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket.app.state.clients.add(websocket)
    clients = websocket.app.state.clients
    print(f"[INFO] Client connected | Total: {len(clients)}")

    try:
        while True:
            data = await websocket.receive()

            # ✅ Clean disconnect — exit loop
            if data["type"] == "websocket.disconnect":
                break

            # ✅ Respond to frontend keepalive ping so Render doesn't
            #    close the idle connection after 30 s
            if data.get("type") == "websocket.receive":
                text = data.get("text", "")
                if text == "ping":
                    await websocket.send_text("pong")

    except WebSocketDisconnect:
        print("[INFO] Client disconnected normally")
    except Exception as e:
        print(f"[ERROR] WebSocket error: {type(e).__name__}: {e}")
    finally:
        clients.discard(websocket)
        print(f"[INFO] Client removed | Total: {len(clients)}")

# ── Entry point ────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
