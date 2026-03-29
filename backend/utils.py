import random
import logging

log = logging.getLogger("utils")

try:
    from sklearn.ensemble import RandomForestClassifier
    import numpy as np

    # Train a simple model on startup
    X_train = [
        [18, 0, 0], [25, 1, 1], [35, 0, 2], [45, 1, 3],
        [22, 0, 1], [30, 1, 0], [50, 0, 2], [28, 1, 3],
        [19, 0, 0], [40, 1, 1], [33, 0, 3], [55, 1, 2],
    ]
    y_train = [0.2, 0.8, 0.5, 0.7, 0.3, 0.9, 0.4, 0.6, 0.1, 0.75, 0.55, 0.85]
    y_binary = [1 if y > 0.5 else 0 for y in y_train]

    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(X_train, y_binary)

    CATEGORY_MAP = {
        'Finance': 0, 'Gaming': 1, 'News': 2,
        'Travel': 3, 'Tech': 4, 'Health': 5
    }
    DEVICE_MAP = {'Mobile': 0, 'Desktop': 1, 'Tablet': 2}

    def predict_ctr(ad: dict) -> float:
        age      = int(ad.get("age", 30))
        category = CATEGORY_MAP.get(ad.get("category", "News"), 2)
        device   = DEVICE_MAP.get(ad.get("device", "Mobile"), 0)

        features  = [[age, category, device]]
        proba     = model.predict_proba(features)[0][1]  # probability of class 1

        # Add small noise so scores aren't too repetitive
        noise = random.uniform(-0.05, 0.05)
        return round(min(max(proba + noise, 0.01), 0.99), 3)

    log.info("✅ ML model loaded successfully")

except ImportError:
    log.warning("⚠️ sklearn not found — using heuristic scoring fallback")

    CATEGORY_SCORES = {
        'Finance': 0.75, 'Gaming': 0.65, 'Tech': 0.70,
        'Travel': 0.55,  'News': 0.45,   'Health': 0.60
    }
    DEVICE_SCORES = {'Desktop': 0.10, 'Mobile': 0.0, 'Tablet': 0.05}

    def predict_ctr(ad: dict) -> float:
        base   = CATEGORY_SCORES.get(ad.get("category", "News"), 0.5)
        device = DEVICE_SCORES.get(ad.get("device", "Mobile"), 0.0)
        age    = int(ad.get("age", 30))

        # Age curve: 25-40 converts best
        age_bonus = 0.1 if 25 <= age <= 40 else -0.05

        score = base + device + age_bonus + random.uniform(-0.08, 0.08)
        return round(min(max(score, 0.01), 0.99), 3)
