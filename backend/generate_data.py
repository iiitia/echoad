import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

# Configuration
rows = 1000
categories = ['news', 'gaming', 'finance', 'social', 'travel']
devices = ['mobile', 'desktop']
regions = ['north', 'south', 'east', 'west']
positions = ['top', 'sidebar', 'feed']

data = []
start_time = datetime(2026, 3, 28, 8, 0, 0)

for i in range(rows):
    ad_id = hex(random.getrandbits(24))[2:]
    timestamp = start_time + timedelta(seconds=i*random.randint(1, 5))
    cat = random.choice(categories)
    dev = random.choice(devices)
    reg = random.choice(regions)
    age = random.randint(18, 65)
    pos = random.choice(positions)

    base_bid = random.uniform(0.1, 2.0)
    if cat == 'finance': base_bid *= 2.5
    if cat == 'travel': base_bid *= 1.8

    click_prob = 0.1
    if dev == 'mobile': click_prob += 0.2
    if cat in ['finance', 'travel'] and pos == 'top': click_prob += 0.3
    if base_bid > 2.0: click_prob += 0.1

    click = 1 if random.random() < click_prob else 0

    data.append([ad_id, timestamp, cat, dev, reg, age, round(base_bid, 2), pos, click])

df = pd.DataFrame(data, columns=[
    'ad_id', 'timestamp', 'site_category', 'device_type',
    'user_region', 'user_age', 'bid_price', 'ad_position', 'click'
])
df.to_csv('ad_logs.csv', index=False)
print("Successfully generated ad_logs.csv with 1000 rows.")