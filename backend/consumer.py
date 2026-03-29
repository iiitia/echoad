import asyncio
import logging
from datetime import datetime
from utils import predict_ctr

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("consumer")

# ── Stats tracker ─────────────────────────────────────────────
stats = {
    "total":      0,
    "high_value": 0,
    "errors":     0,
    "start_time": datetime.now(),
}

def log_stats():
    elapsed  = (datetime.now() - stats["start_time"]).seconds or 1
    rate     = stats["total"] / elapsed * 60
    high_pct = (stats["high_value"] / max(stats["total"], 1)) * 100
    log.info(
        f"📊 Total={stats['total']} | "
        f"HighValue={stats['high_value']} ({high_pct:.1f}%) | "
        f"Errors={stats['errors']} | "
        f"Rate={rate:.1f} ads/min"
    )

# ── Main consumer ─────────────────────────────────────────────
async def consumer(queue: asyncio.Queue, clients: set):
    log.info("✅ Consumer started — waiting for ads...")

    while True:
        try:
            ad = await queue.get()

            # ── Validate required fields ───────────────────────
            required = {"ad_id", "timestamp", "category", "device", "age"}
            missing  = required - set(ad.keys())
            if missing:
                log.warning(f"⚠️  Skipping ad — missing fields: {missing} | ad={ad}")
                queue.task_done()
                stats["errors"] += 1
                continue

            # ── Predict CTR score ──────────────────────────────
            try:
                ad["score"] = predict_ctr(ad)
            except Exception as e:
                log.error(f"❌ predict_ctr crashed: {e} | ad={ad}")
                ad["score"] = 0.0
                stats["errors"] += 1

            # ── Update stats ───────────────────────────────────
            stats["total"] += 1
            if ad["score"] > 0.7:
                stats["high_value"] += 1

            if stats["total"] % 10 == 0:
                log_stats()

            # ── Classify ad tier ───────────────────────────────
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

            # ── Broadcast to all WebSocket clients ─────────────
            if not clients:
                log.debug("No clients connected — ad processed but not sent")
                queue.task_done()
                continue

            dead_clients = set()

            await asyncio.gather(*[
                _send(client, ad, dead_clients)
                for client in clients.copy()
            ], return_exceptions=True)

            # ── Clean up disconnected clients ──────────────────
            if dead_clients:
                clients -= dead_clients
                log.info(f"🔌 Removed {len(dead_clients)} dead client(s) | Active={len(clients)}")

            queue.task_done()

        except asyncio.CancelledError:
            log.info("🛑 Consumer cancelled — shutting down")
            break

        except Exception as e:
            log.error(f"❌ Unexpected consumer error: {e}")
            queue.task_done()

# ── Safe send helper ──────────────────────────────────────────
async def _send(client, ad: dict, dead_clients: set):
    """Sends ad to one client. Marks client dead on any error."""
    try:
        # Guard: only send to fully connected clients
        # WebSocketState.CONNECTED == 1
        if client.client_state.value != 1:
            dead_clients.add(client)
            return

        await asyncio.wait_for(
            client.send_json(ad),
            timeout=3.0
        )

    except asyncio.TimeoutError:
        log.warning("⏱️  Client send timeout — marking dead")
        dead_clients.add(client)

    except Exception as e:
        log.warning(f"⚠️  Client send failed: {type(e).__name__} — marking dead")
        dead_clients.add(client)
