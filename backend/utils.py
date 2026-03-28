
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import joblib
import pandas as pd
import numpy as np

# ✅ Get correct path (works locally + Render)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

model_path = os.path.join(BASE_DIR, "model.pkl")
encoder_path = os.path.join(BASE_DIR, "encoder.pkl")

# ✅ Load files
model = joblib.load(model_path)
device_encoder, category_encoder, catdev_encoder = joblib.load(encoder_path)
print("[OK] model.pkl and encoder.pkl loaded successfully")

# ── Safe label encoder helper ─────────────────────────────────────────────────
def safe_encode(encoder, val):
    val = str(val).strip().lower()
    if val in encoder.classes_:
        return int(encoder.transform([val])[0])
    return 0

# ── Feature builder ───────────────────────────────────────────────────────────
def build_features(ad: dict) -> list:
    """
    Converts raw ad dict -> 14-feature vector matching updated model.py.
    FEATURES = [
        age, age_sq, age_bucket, is_young, is_prime, is_senior,
        device_enc, is_mobile,
        category_enc, cat_risk,
        cat_device, mobile_young, mobile_prime, age_x_mobile
    ]
    """

    # ── Age features ───────────────────────────────────────────────────────
    age         = float(ad.get("age", 30))
    age_sq      = age ** 2
    age_bucket_raw = pd.cut(
        [age],
        bins=[0, 18, 25, 35, 50, 65, 100],
        labels=[0, 1, 2, 3, 4, 5]
    )[0]
    age_bucket  = int(age_bucket_raw) if pd.notna(age_bucket_raw) else 2
    is_young    = int(age < 25)
    is_prime    = int(25 <= age <= 44)
    is_senior   = int(age > 55)

    # ── Device features ────────────────────────────────────────────────────
    device_raw  = str(ad.get("device", "")).strip().lower()
    device_enc  = safe_encode(device_encoder, device_raw)
    is_mobile   = int(device_raw == "mobile")

    # ── Category features ──────────────────────────────────────────────────
    category_raw = str(ad.get("category", "")).strip().lower()
    category_enc = safe_encode(category_encoder, category_raw)

    HIGH_CTR_CATS = {"gaming", "tech", "finance", "sports"}
    MED_CTR_CATS  = {"travel", "news", "health"}
    cat_risk = (
        2 if category_raw in HIGH_CTR_CATS else
        1 if category_raw in MED_CTR_CATS  else
        0
    )

    # ── Interaction features ───────────────────────────────────────────────
    cat_device_raw = category_raw + "_" + device_raw
    catdev_enc     = safe_encode(catdev_encoder, cat_device_raw)
    mobile_young   = is_mobile * is_young
    mobile_prime   = is_mobile * is_prime
    age_x_mobile   = age * is_mobile

    return [[
        # Age signals
        age,            # 1.  raw age
        age_sq,         # 2.  age squared (non-linear effect)
        age_bucket,     # 3.  age group bucket
        is_young,       # 4.  age < 25
        is_prime,       # 5.  age 25-44
        is_senior,      # 6.  age > 55

        # Device signals
        device_enc,     # 7.  encoded device
        is_mobile,      # 8.  binary mobile flag

        # Category signals
        category_enc,   # 9.  encoded category
        cat_risk,       # 10. category CTR risk score

        # Interaction signals
        catdev_enc,     # 11. category x device interaction
        mobile_young,   # 12. mobile AND young
        mobile_prime,   # 13. mobile AND prime age
        age_x_mobile,   # 14. continuous age x mobile
    ]]

# ── Main prediction function (called by consumer.py) ─────────────────────────
def predict_ctr(ad: dict) -> float:
    """
    Returns a float CTR score between 0.0 and 1.0.
    Safe against missing fields, unseen categories, bad data.
    """
    try:
        features = build_features(ad)
        score    = model.predict_proba(features)[0][1]
        return round(float(score), 4)
    except Exception as e:
        print("[WARN] predict_ctr failed:", str(e), "| ad:", ad)
        return 0.0