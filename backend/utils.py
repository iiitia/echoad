import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import joblib

# ✅ Paths (works locally + Render)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

model_path = os.path.join(BASE_DIR, "model.pkl")
encoder_path = os.path.join(BASE_DIR, "encoder.pkl")

# ✅ Load model + encoders safely
try:
    model = joblib.load(model_path)
    device_encoder, category_encoder, catdev_encoder = joblib.load(encoder_path)
    print("[OK] model and encoders loaded")
except Exception as e:
    print("[WARN] Model loading failed:", e)
    model = None
    device_encoder = category_encoder = catdev_encoder = None


# ── Safe encoder ─────────────────────────────────────────────
def safe_encode(encoder, val):
    if encoder is None:
        return 0
    val = str(val).strip().lower()
    if val in encoder.classes_:
        return int(encoder.transform([val])[0])
    return 0


# ── Feature builder (NO pandas) ─────────────────────────────
def build_features(ad: dict) -> list:

    # Age features
    age = float(ad.get("age", 30))
    age_sq = age ** 2

    if age < 18:
        age_bucket = 0
    elif age < 25:
        age_bucket = 1
    elif age < 35:
        age_bucket = 2
    elif age < 50:
        age_bucket = 3
    elif age < 65:
        age_bucket = 4
    else:
        age_bucket = 5

    is_young = int(age < 25)
    is_prime = int(25 <= age <= 44)
    is_senior = int(age > 55)

    # Device
    device_raw = str(ad.get("device", "")).strip().lower()
    device_enc = safe_encode(device_encoder, device_raw)
    is_mobile = int(device_raw == "mobile")

    # Category
    category_raw = str(ad.get("category", "")).strip().lower()
    category_enc = safe_encode(category_encoder, category_raw)

    HIGH_CTR_CATS = {"gaming", "tech", "finance", "sports"}
    MED_CTR_CATS = {"travel", "news", "health"}

    if category_raw in HIGH_CTR_CATS:
        cat_risk = 2
    elif category_raw in MED_CTR_CATS:
        cat_risk = 1
    else:
        cat_risk = 0

    # Interactions
    cat_device_raw = category_raw + "_" + device_raw
    catdev_enc = safe_encode(catdev_encoder, cat_device_raw)

    mobile_young = is_mobile * is_young
    mobile_prime = is_mobile * is_prime
    age_x_mobile = age * is_mobile

    return [[
        age,
        age_sq,
        age_bucket,
        is_young,
        is_prime,
        is_senior,
        device_enc,
        is_mobile,
        category_enc,
        cat_risk,
        catdev_enc,
        mobile_young,
        mobile_prime,
        age_x_mobile,
    ]]


# ── Prediction ─────────────────────────────────────────────
def predict_ctr(ad: dict) -> float:
    try:
        if model is None:
            return 0.5  # fallback

        features = build_features(ad)
        score = model.predict_proba(features)[0][1]
        return round(float(score), 4)

    except Exception as e:
        print("[WARN] predict_ctr failed:", e)
        return 0.0
