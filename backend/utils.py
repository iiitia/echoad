


import random
import logging
import httpx
import os

log = logging.getLogger("utils")

ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "")

def predict_ctr(ad: dict) -> float:
    """Heuristic scoring — no ML deps needed on Render."""
    CATEGORY_SCORES = {
        'Finance': 0.75, 'Gaming': 0.65, 'Tech': 0.70,
        'Travel': 0.55,  'News':  0.45,  'Health': 0.60
    }
    base      = CATEGORY_SCORES.get(ad.get("category", "News"), 0.5)
    age       = int(ad.get("age", 30))
    age_bonus = 0.1 if 25 <= age <= 40 else -0.05
    score     = base + age_bonus + random.uniform(-0.08, 0.08)
    return round(min(max(score, 0.01), 0.99), 3)
