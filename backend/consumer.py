import asyncio
import json
import logging
from datetime import datetime
from utils import predict_ctr
# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("consumer")

# ── Stats tracker (in-memory, resets on restart) ──────────────────────────────
stats = {
    "total":      0,
    "high_value": 0,   # score > 0.7
    "errors":     0,
    "start_time": datetime.now(),
}

def log_stats():
    """Print a summary line every 10 ads."""
    elapsed  = (datetime.now() - stats["start_time"]).seconds or 1
    rate     = stats["total"] / elapsed * 60   # ads per minute
    high_pct = (stats["high_value"] / max(stats["total"], 1)) * 100
    log.info(
        f"📊 Total={stats['total']} | "
        f"HighValue={stats['high_value']} ({high_pct:.1f}%) | "
        f"Errors={stats['errors']} | "
        f"Rate={rate:.1f} ads/min"
    )

# ── Main consumer ─────────────────────────────────────────────────────────────
async def consumer(queue, clients):
    log.info("✅ Consumer started — waiting for ads...")

    while True:
        # ── Get next ad from queue ─────────────────────────────────────────
        ad = await queue.get()

        # ── Validate required fields ───────────────────────────────────────
        required = {"ad_id", "timestamp", "category", "device", "age"}
        missing  = required - set(ad.keys())
        if missing:
            log.warning(f"⚠️  Skipping ad — missing fields: {missing} | ad={ad}")
            queue.task_done()
            stats["errors"] += 1
            continue

        # ── Predict CTR score ──────────────────────────────────────────────
        try:
            ad["score"] = predict_ctr(ad)
        except Exception as e:
            log.error(f"❌ predict_ctr crashed: {e} | ad={ad}")
            ad["score"] = 0.0
            stats["errors"] += 1

        # ── Update stats ───────────────────────────────────────────────────
        stats["total"] += 1
        if ad["score"] > 0.7:
            stats["high_value"] += 1

        if stats["total"] % 10 == 0:
            log_stats()

        # ── Classify ad tier (sent to frontend) ───────────────────────────
        ad["tier"] = (
            "high"   if ad["score"] > 0.7 else
            "medium" if ad["score"] > 0.4 else
            "low"
        )

        log.info(
            f"🔵 [{ad['tier'].upper():6}] {ad['ad_id']} | "
            f"score={ad['score']:.3f} | "
            f"cat={ad['category']} | dev={ad['device']}"
        )

        # ── Broadcast to all WebSocket clients ────────────────────────────
        if not clients:
            log.debug("No clients connected — ad processed but not sent")
            queue.task_done()
            continue

        dead_clients = set()

        await asyncio.gather(*[
            _send(client, ad, dead_clients)
            for client in clients.copy()
        ], return_exceptions=True)

        # ── Clean up disconnected clients ──────────────────────────────────
        if dead_clients:
            clients -= dead_clients
            log.info(f"🔌 Removed {len(dead_clients)} dead client(s) | Active={len(clients)}")

        queue.task_done()

# ── Safe send helper ──────────────────────────────────────────────────────────
async def _send(client, ad: dict, dead_clients: set):
    """Sends ad to one client. Marks client dead on any error."""
    try:
        await asyncio.wait_for(
            client.send_json(ad),
            timeout=3.0   # don't let a slow client block the whole queue
        )
    except asyncio.TimeoutError:
        log.warning(f"⏱️  Client send timeout — marking dead")
        dead_clients.add(client)
    except Exception as e:
        log.warning(f"⚠️  Client send failed: {type(e).__name__} — marking dead")
        dead_clients.add(client)
