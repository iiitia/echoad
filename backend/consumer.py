import asyncio
import logging
from datetime import datetime
from utils import predict_ctr

log = logging.getLogger("consumer")

RING_BUFFER_SIZE = 50

stats = {
    "total":      0,
    "high_value": 0,
    "errors":     0,
    "start_time": datetime.now(),
}

def log_stats():
    elapsed = (datetime.now() - stats["start_time"]).seconds or 1
    rate     = stats["total"] / elapsed * 60
    high_pct = (stats["high_value"] / max(stats["total"], 1)) * 100
    log.info(
        f"📊 Total={stats['total']} | "
        f"HighValue={stats['high_value']} ({high_pct:.1f}%) | "
        f"Errors={stats['errors']} | "
        f"Rate={rate:.1f} ads/min"
    )

async def broadcast(clients: set, data: dict):
    """
    Send JSON to every connected client.
    Dead / errored clients are collected and removed from the set
    so they don't accumulate and cause repeated failures.
    """
    dead = set()
    for client in clients:
        try:
            await client.send_json(data)
        except Exception:
            # Client is gone — mark for removal
            dead.add(client)

    # ✅ Remove dead clients AFTER iterating (never mutate a set while looping it)
    if dead:
        clients -= dead
        log.info(f"🧹 Removed {len(dead)} dead client(s) | Active: {len(clients)}")

async def consumer(queue: asyncio.Queue, clients: set, recent_ads: list):
    log.info("✅ Consumer started — waiting for ads...")

    while True:
        try:
            ad = await queue.get()

            # ── Score ──────────────────────────────────────────
            try:
                score = predict_ctr(ad)
            except Exception as e:
                stats["errors"] += 1
                log.error(f"❌ predict_ctr failed: {e}")
                queue.task_done()
                continue

            # ── Build payload ──────────────────────────────────
            data = {
                "ad_id":     ad.get("ad_id"),
                "category":  ad.get("category"),
                "device":    ad.get("device"),
                "timestamp": ad.get("timestamp"),
                "score":     score,
            }

            # ── Ring buffer ────────────────────────────────────
            recent_ads.append(data)
            if len(recent_ads) > RING_BUFFER_SIZE:
                recent_ads.pop(0)

            # ── Stats ──────────────────────────────────────────
            stats["total"] += 1
            if score > 0.7:
                stats["high_value"] += 1

            # ── Broadcast to live WebSocket clients ────────────
            if clients:
                await broadcast(clients, data)

            log.info(f"🔵 Processed: {data['ad_id']} | score={score:.3f} | clients={len(clients)}")
            queue.task_done()

        except asyncio.CancelledError:
            log.info("🛑 Consumer stopped")
            break

        except Exception as e:
            stats["errors"] += 1
            log.error(f"❌ Unexpected error in consumer: {e}")
