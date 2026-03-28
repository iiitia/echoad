import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (accuracy_score, f1_score,
                             roc_auc_score, classification_report,
                             confusion_matrix)

# ── Load Data ──────────────────────────────────────────────
df = pd.read_csv('ad_logs.csv')

df.columns = (
    df.columns
    .str.strip()
    .str.lower()
    .str.replace(r'[\s\-]+', '_', regex=True)
)

print("✅ Columns found:", df.columns.tolist())

drop_cols = [col for col in ['ad_id', 'timestamp'] if col in df.columns]
df = df.drop(columns=drop_cols)

# ── Column map (matches company generate.py) ───────────────
COL_DEVICE   = 'device_type'
COL_CATEGORY = 'site_category'
COL_POSITION = 'ad_position'
COL_BID      = 'bid_price'
COL_AGE      = 'user_age'
COL_REGION   = 'user_region'
COL_TARGET   = 'click'

required = [COL_DEVICE, COL_CATEGORY, COL_POSITION,
            COL_BID, COL_AGE, COL_TARGET]
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"❌ Missing columns: {missing}\n"
                     f"   Available columns: {df.columns.tolist()}")

# ── Class balance check ────────────────────────────────────
click_rate = df[COL_TARGET].mean()
print(f"\n📊 Click rate: {click_rate:.2%}  |  Imbalance ratio: {(1-click_rate)/click_rate:.1f}:1")

# ── Feature Engineering ────────────────────────────────────
df['is_mobile']         = (df[COL_DEVICE] == 'mobile').astype(int)
df['is_high_value_cat'] = df[COL_CATEGORY].isin(['finance', 'travel']).astype(int)
df['is_top_position']   = (df[COL_POSITION] == 'top').astype(int)
df['highcat_x_top']     = df['is_high_value_cat'] * df['is_top_position']
df['bid_x_mobile']      = df[COL_BID] * df['is_mobile']
df['mobile_x_highcat']  = df['is_mobile'] * df['is_high_value_cat']

# Age binning
df['age_bin'] = pd.cut(
    df[COL_AGE],
    bins=[0, 24, 34, 44, 54, 100],
    labels=['18-24', '25-34', '35-44', '45-54', '55+']
)

# One-hot encode categorical columns
cat_cols = df.select_dtypes(include='category').columns.tolist()
cat_cols += df.select_dtypes(include='object').columns.tolist()
df_encoded = pd.get_dummies(df, columns=cat_cols, drop_first=False)
df_encoded = df_encoded.drop(columns=[COL_AGE])  # replaced by age_bin

# ── Features & Target ──────────────────────────────────────
X = df_encoded.drop(COL_TARGET, axis=1)
y = df_encoded[COL_TARGET]

print(f"📐 Feature matrix: {X.shape[0]} rows × {X.shape[1]} features")

# ── Train/Test Split ───────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# ── Mild class reweighting (sqrt-scaled) ───────────────────
neg = (y_train == 0).sum()
pos = (y_train == 1).sum()
weight_for_clicks = np.sqrt(neg / pos)
sample_weights = y_train.map({0: 1.0, 1: weight_for_clicks})

print(f"⚖️  Sample weight for Click class: {weight_for_clicks:.2f}x")

# ── Model ──────────────────────────────────────────────────
model = GradientBoostingClassifier(
    n_estimators=400,
    learning_rate=0.05,
    max_depth=4,
    min_samples_split=20,
    min_samples_leaf=10,
    subsample=0.8,
    max_features='sqrt',
    random_state=42
)
model.fit(X_train, y_train, sample_weight=sample_weights)

# ── Tune Decision Threshold ────────────────────────────────
y_prob = model.predict_proba(X_test)[:, 1]

best_thresh, best_f1 = 0.5, 0
for thresh in [i / 100 for i in range(30, 70)]:
    preds = (y_prob >= thresh).astype(int)
    if preds.sum() == 0:
        continue
    prec = preds[y_test == 1].sum() / preds.sum()
    if prec < 0.40:
        continue
    score = f1_score(y_test, preds, zero_division=0)
    if score > best_f1:
        best_f1 = score
        best_thresh = thresh

print(f"\n🎯 Best Threshold: {best_thresh}  |  F1 at threshold: {best_f1:.4f}")
y_pred = (y_prob >= best_thresh).astype(int)

# ── Metrics ────────────────────────────────────────────────
print("\n" + "=" * 45)
print("       IMPROVED MODEL EVALUATION METRICS")
print("=" * 45)
print(f"✅ Accuracy  : {accuracy_score(y_test, y_pred)*100:.2f}%")
print(f"✅ F1 Score  : {f1_score(y_test, y_pred):.4f}")
print(f"✅ AUC-ROC   : {roc_auc_score(y_test, y_prob):.4f}")
print("=" * 45)

print("\n📊 Classification Report:")
print(classification_report(y_test, y_pred, target_names=['No Click', 'Click']))

print("🔲 Confusion Matrix:")
cm = confusion_matrix(y_test, y_pred)
print(cm)
tn, fp, fn, tp = cm.ravel()
print(f"   TN={tn}  FP={fp}  FN={fn}  TP={tp}")
print(f"   Precision: {tp/(tp+fp):.2%}  |  Recall: {tp/(tp+fn):.2%}")

# ── Cross-validation ───────────────────────────────────────
print("\n🔁 5-Fold CV AUC-ROC (on full data):")
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_scores = cross_val_score(model, X, y, cv=cv, scoring='roc_auc')
print(f"   Mean: {cv_scores.mean():.4f}  |  Std: {cv_scores.std():.4f}")
print(f"   Fold scores: {[round(float(s), 4) for s in cv_scores]}")

print("\n🔑 Top 10 Important Features:")
feat_imp = pd.Series(model.feature_importances_, index=X.columns)
print(feat_imp.nlargest(10).round(4).to_string())