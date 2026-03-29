import asyncio
import logging
from datetime import datetime
from utils import predict_ctr

log = logging.getLogger("consumer")

RING_BUFFER_SIZE = 50

stats = {
    "total": 0,
    "high_value": 0,
    "errors": 0,
    "start_time": datetime.now(),
}

def log_stats():
    elapsed = (datetime.now() - stats["start_time"]).seconds or 1
    rate = stats["total"] / elapsed * 60
    high_pct = (stats["high_value"] / max(stats["total"], 1)) * 100

    log.info(
        f"📊 Total={stats['total']} | "
        f"HighValue={stats['high_value']} ({high_pct:.1f}%) | "
        f"Errors={stats['errors']} | "
        f"Rate={rate:.1f} ads/min"
    )

# ✅ FINAL FIXED CONSUMER
async def consumer(queue: asyncio.Queue, clients: set, recent_ads: list):
    log.info("✅ Consumer started — waiting for ads...")

    while True:
        try:
            ad = await queue.get()

            score = predict_ctr(ad)

            data = {
                "ad_id": ad.get("ad_id"),
                "category": ad.get("category"),
                "device": ad.get("device"),
                "timestamp": ad.get("timestamp"),
                "score": score,
            }

            # 🔥 STORE DATA
            recent_ads.append(data)

            # keep buffer size
            if len(recent_ads) > RING_BUFFER_SIZE:
                recent_ads.pop(0)

            # stats
            stats["total"] += 1
            if score > 0.7:
                stats["high_value"] += 1

            # optional WebSocket
            for client in clients:
                try:
                    await client.send_json(data)
                except:
                    pass

            log.info(f"🔵 Processed: {data['ad_id']} | score={score}")

            queue.task_done()

        except asyncio.CancelledError:
            log.info("🛑 Consumer stopped")
            break

        except Exception as e:
            stats["errors"] += 1
            log.error(f"❌ Error: {e}")
