import sys
sys.stdout.reconfigure(encoding='utf-8')

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from backend.producer import producer
from backend.consumer import consumer
# ── Shared state ──────────────────────────────────────────────────────────────
queue   = asyncio.Queue()
clients = set()

# ── Lifespan (replaces deprecated @app.on_event) ──────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    asyncio.create_task(producer(queue))
    asyncio.create_task(consumer(queue, clients))
    print("[OK] Backend started -- Producer and Consumer running")
    print("[OK] WebSocket ready at ws://localhost:8000/ws")
    yield
    # Shutdown (runs when server stops)
    print("[INFO] Backend shutting down...")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="EchoAd - Real-Time Ad Bidding Simulator",
    lifespan=lifespan
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── HTTP Routes ───────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "status":    "running",
        "message":   "EchoAd Backend is live",
        "websocket": "ws://localhost:8000/ws",
        "clients":   len(clients),
        "queue":     queue.qsize(),
    }

@app.get("/health")
async def health():
    return {
        "status":          "ok",
        "connected_clients": len(clients),
        "queue_size":      queue.qsize(),
    }

@app.get("/stats")
async def stats():
    return {
        "connected_clients": len(clients),
        "queue_size":        queue.qsize(),
    }

# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    print(f"[INFO] Client connected  | Total clients: {len(clients)}")

    try:
        while True:
            # Keep connection alive — wait for ping from frontend
            data = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=60.0  # disconnect if no ping for 60s
            )
    except asyncio.TimeoutError:
        print("[WARN] Client timed out -- no ping received in 60s")
    except WebSocketDisconnect:
        print(f"[INFO] Client disconnected | Total clients: {len(clients) - 1}")
    except Exception as e:
        print(f"[WARN] WebSocket error: {type(e).__name__}: {e}")
    finally:
        clients.discard(websocket)
        print(f"[INFO] Client removed | Total clients: {len(clients)}")

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )