import sys
sys.stdout.reconfigure(encoding='utf-8')

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# ✅ Correct imports (important for Render)
from backend.producer import producer
from backend.consumer import consumer

# ── Shared state ──────────────────────────────────────────────
queue = asyncio.Queue()
clients = set()

# ── Lifespan (startup / shutdown) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    producer_task = asyncio.create_task(producer(queue))
    consumer_task = asyncio.create_task(consumer(queue, clients))

    print("✅ Backend started (Render-ready)")
    print("🌐 WebSocket endpoint: /ws")

    yield

    print("🛑 Backend shutting down...")
    producer_task.cancel()
    consumer_task.cancel()

# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="EchoAd - Real-Time Ad Bidding Simulator",
    lifespan=lifespan
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── HTTP Routes ───────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "EchoAd Backend is live",
        "websocket": "/ws",
        "clients": len(clients),
        "queue": queue.qsize(),
    }

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "connected_clients": len(clients),
        "queue_size": queue.qsize(),
    }

@app.get("/stats")
async def stats():
    return {
        "connected_clients": len(clients),
        "queue_size": queue.qsize(),
    }

# ── WebSocket ─────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)

    print(f"[INFO] Client connected | Total: {len(clients)}")

    try:
        while True:
            # Receive ping from frontend to keep connection alive
            await websocket.receive_text()

    except WebSocketDisconnect:
        print("[INFO] Client disconnected")

    except Exception as e:
        print(f"[ERROR] WebSocket error: {type(e).__name__}: {e}")

    finally:
        clients.discard(websocket)
        print(f"[INFO] Client removed | Total: {len(clients)}")
