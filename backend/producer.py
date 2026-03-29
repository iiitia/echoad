import asyncio
import random
import logging
from datetime import datetime

log = logging.getLogger("producer")

CATEGORIES = ['Finance', 'Gaming', 'News', 'Travel']
DEVICES    = ['Mobile', 'Desktop']

async def producer(queue: asyncio.Queue):
    log.info("🟢 Producer started — generating ads every 2s")

    while True:
        try:
            ad = {
                "ad_id":     hex(random.getrandbits(24))[2:],
                "category":  random.choice(CATEGORIES),
                "device":    random.choice(DEVICES),
                "age":       random.randint(18, 65),
                "timestamp": datetime.now().isoformat(),
            }

            await queue.put(ad)
            log.info(f"🟢 Produced: {ad['ad_id']} | cat={ad['category']} | dev={ad['device']}")

        except asyncio.CancelledError:
            log.info("🛑 Producer cancelled — shutting down")
            break

        except Exception as e:
            log.error(f"❌ Producer error: {e}")

        await asyncio.sleep(2)
