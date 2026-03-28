import asyncio
import random
from datetime import datetime

categories = ['Finance', 'Gaming', 'News', 'Travel']
devices = ['Mobile', 'Desktop']

async def producer(queue):
    while True:
        ad = {
            "ad_id": hex(random.getrandbits(24))[2:],
            "category": random.choice(categories),
            "device": random.choice(devices),
            "age": random.randint(18, 65),
            "timestamp": datetime.now().isoformat()
        }

        await queue.put(ad)
        print("🟢 Produced:", ad)

        await asyncio.sleep(2)