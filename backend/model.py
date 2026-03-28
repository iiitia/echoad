import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.utils.class_weight import compute_sample_weight
import joblib
import warnings
warnings.filterwarnings("ignore")

# ── Load ──────────────────────────────────────────────────────────────────────
df = pd.read_csv("ad_logs.csv")

RENAME_MAP = {
    "site_category": "category",
    "ad_category":   "category",
    "device_type":   "device",
    "device_name":   "device",
    "user_age":      "age",
    "Age":           "age",
    "clicked":       "click",
    "is_click":      "click",
    "label":         "click",
    "target":        "click",
    "ctr":           "click",
}
df = df.rename(columns=RENAME_MAP)

print("[INFO] Columns  :", df.columns.tolist())
print("[INFO] Rows     :", len(df))
print("[INFO] Click rate:", round(df["click"].mean() * 100, 2), "%")

# ── Feature Engineering ───────────────────────────────────────────────────────

# 1. Clean
df["age"]      = pd.to_numeric(df["age"], errors="coerce").fillna(30)
df["category"] = df["category"].astype(str).str.strip().str.lower()
df["device"]   = df["device"].astype(str).str.strip().str.lower()

# 2. Age features — most important signal in your data (0.57 importance)
df["age_bucket"] = pd.cut(
    df["age"],
    bins=[0, 18, 25, 35, 50, 65, 100],
    labels=[0, 1, 2, 3, 4, 5]
).astype(float).fillna(2).astype(int)

df["age_sq"]       = df["age"] ** 2                    # non-linear age effect
df["is_young"]     = (df["age"] < 25).astype(int)      # 18-24 high CTR segment
df["is_prime"]     = df["age"].between(25, 44).astype(int)  # prime buying age
df["is_senior"]    = (df["age"] > 55).astype(int)      # lower CTR segment

# 3. Interaction features — category x device was 0.13 importance, expand it
df["cat_device"]        = df["category"] + "_" + df["device"]
df["is_mobile"]         = (df["device"] == "mobile").astype(int)
df["mobile_young"]      = df["is_mobile"] * df["is_young"]   # mobile + young = high CTR
df["mobile_prime"]      = df["is_mobile"] * df["is_prime"]
df["age_x_mobile"]      = df["age"] * df["is_mobile"]        # continuous interaction

# 4. Category risk score — encode business knowledge
HIGH_CTR_CATS  = {"gaming", "tech", "finance", "sports"}
MED_CTR_CATS   = {"travel", "news", "health"}
df["cat_risk"] = df["category"].apply(
    lambda c: 2 if c in HIGH_CTR_CATS else (1 if c in MED_CTR_CATS else 0)
)

# ── Encode Categoricals ───────────────────────────────────────────────────────
device_encoder   = LabelEncoder()
category_encoder = LabelEncoder()
catdev_encoder   = LabelEncoder()

df["device_enc"]   = device_encoder.fit_transform(df["device"])
df["category_enc"] = category_encoder.fit_transform(df["category"])
df["cat_device"]   = catdev_encoder.fit_transform(df["cat_device"])

# ── Feature Matrix ────────────────────────────────────────────────────────────
FEATURES = [
    # Age signals (your strongest predictor)
    "age",
    "age_sq",
    "age_bucket",
    "is_young",
    "is_prime",
    "is_senior",

    # Device signals
    "device_enc",
    "is_mobile",

    # Category signals
    "category_enc",
    "cat_risk",

    # Interaction signals
    "cat_device",
    "mobile_young",
    "mobile_prime",
    "age_x_mobile",
]

X = df[FEATURES]
y = df["click"]

print("[INFO] Features used:", len(FEATURES))
print("[INFO] Feature list :", FEATURES)

# ── Train / Test Split ────────────────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

# ── Class Imbalance ───────────────────────────────────────────────────────────
sample_weights = compute_sample_weight(class_weight="balanced", y=y_train)

# ── Model ─────────────────────────────────────────────────────────────────────
model = GradientBoostingClassifier(
    n_estimators=300,       # more trees — better for small dataset
    learning_rate=0.03,     # lower = more robust, less overfit
    max_depth=3,            # shallower = less overfit on 1000 rows
    min_samples_leaf=10,    # tighter control on small data
    subsample=0.8,
    max_features=0.8,       # feature sampling — adds diversity
    random_state=42,
)

print("[START] Training model...")
model.fit(X_train, y_train, sample_weight=sample_weights)

# ── Cross Validation (more reliable than single split on 1000 rows) ───────────
cv      = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_aucs = cross_val_score(model, X, y, cv=cv, scoring="roc_auc")
print("[RESULT] 5-Fold CV AUC:", round(cv_aucs.mean(), 4), "(+-" + str(round(cv_aucs.std(), 4)) + ")")

# ── Test Set Evaluation ───────────────────────────────────────────────────────
y_pred = model.predict(X_test)
y_prob = model.predict_proba(X_test)[:, 1]
auc    = roc_auc_score(y_test, y_prob)

print("[RESULT] Test AUC    :", round(auc, 4), "(prev: 0.6462)")
print("[RESULT] Classification Report:")
print(classification_report(y_test, y_pred, target_names=["No Click", "Click"]))

# ── Feature Importance ────────────────────────────────────────────────────────
importances = pd.Series(model.feature_importances_, index=FEATURES)
print("[FEATURES] Importance ranking:")
print(importances.sort_values(ascending=False).to_string())

# ── Save ──────────────────────────────────────────────────────────────────────
joblib.dump(model, "model.pkl")
joblib.dump(
    (device_encoder, category_encoder, catdev_encoder),
    "encoder.pkl"
)

print("")
print("[OK] model.pkl   saved -- GradientBoostingClassifier,", len(FEATURES), "features")
print("[OK] encoder.pkl saved -- 3 LabelEncoders")
print("")
print("Next step: python main.py")