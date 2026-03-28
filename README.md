# ⚡ EchoAd — Real-Time Ad Auction Simulator

> End-to-end ML pipeline for Click-Through Rate (CTR) prediction, streamed live to a React dashboard.

---

## Architecture Overview

```
generate_data.py → ad_logs.csv → model.py → model.pkl + encoder.pkl
                                                       ↓
producer.py → asyncio.Queue → consumer.py (ML inference) → WebSocket → React Dashboard
```

---

## Infrastructure Decision: Kafka → asyncio.Queue

This project was architected for **Apache Kafka** as the messaging backbone. During setup, Kafka encountered Docker port binding conflicts on the local environment.

Per the assignment brief's approved fallback guidelines, the pipeline was **refactored to Python's `asyncio.Queue` (Fallback B)** — running producer and consumer as FastAPI background tasks within the same process.

This fallback:
- Preserves the **exact producer-consumer architecture** Kafka would provide
- Maintains **decoupled, async message passing**
- Handles the required ~30 ads/min throughput with zero performance impact
- Can be swapped back to Kafka by replacing the queue with a `kafka-python` producer/consumer with minimal code changes

---

## ML Model Decision: GradientBoosting over Logistic Regression

The brief suggested Logistic Regression as a starting point. After evaluating both on the dataset:

| Model | AUC-ROC | Accuracy | F1 Score |
|---|---|---|---|
| Logistic Regression | ~0.58 | ~61% | ~0.38 |
| **GradientBoostingClassifier** | **~0.69** | **~73%** | **~0.43** |

GradientBoosting was chosen for its significantly better performance on the imbalanced dataset (73% No-Click vs 27% Click). It also naturally handles non-linear feature interactions like `bid_price × device` and `category × position` which are critical signals in CTR prediction.

---

## Tech Stack

### Backend
| Component | Tool | Purpose |
|---|---|---|
| API Server | FastAPI 0.115.0 + Uvicorn 0.32.0 | HTTP + WebSocket endpoints |
| ML Model | scikit-learn 1.5.2 (GradientBoostingClassifier) | CTR prediction |
| Data Processing | pandas 2.2.3, numpy, joblib 1.4.2 | Feature engineering + serialization |
| Async Pipeline | asyncio.Queue | Producer-consumer (Kafka fallback) |
| Dataset | ad_logs.csv (1000 synthetic rows) | age, device, category → click (0/1) |

### Frontend
| Component | Tool | Purpose |
|---|---|---|
| Build Tool | Vite 5.2.0 | Fast dev server |
| UI | React 18.2.0 + TailwindCSS 3.4.13 | Live dashboard |
| Charts | recharts 3.8.1 | CTR trend line chart |
| Fonts | Rajdhani, Share Tech Mono | Monospace dashboard UI |

---

## Project Structure

```
echoad/
├── README.md
├── backend/
│   ├── main.py            # FastAPI app + lifespan (starts producer/consumer)
│   ├── producer.py        # Generates fake ad requests → queue every 2s
│   ├── consumer.py        # queue → ML predict → WebSocket broadcast
│   ├── utils.py           # predict_ctr() inference function
│   ├── model.py           # Train & save GradientBoostingClassifier
│   ├── generate_data.py   # Creates ad_logs.csv (1000 synthetic rows)
│   ├── metrics.py         # Standalone model evaluation script
│   ├── ad_logs.csv        # Training data (regenerate via generate_data.py)
│   ├── model.pkl          # Trained model (regenerate via model.py)
│   ├── encoder.pkl        # LabelEncoders (regenerate via model.py)
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx        # Full dashboard — charts, table, WebSocket
    │   ├── main.jsx       # React root
    │   └── index.css
    ├── index.html
    ├── vite.config.js
    ├── tailwind.config.js
    └── package.json
```

> **Note:** `model.pkl`, `encoder.pkl`, and `ad_logs.csv` are not committed to the repo.
> Generate them locally by following the Quick Start steps below.

---

## Quick Start

### 1. Backend

```bash
cd echoad/backend

# Install dependencies
pip install -r requirements.txt

# Step 1 — Generate synthetic training data
python generate_data.py
# → creates ad_logs.csv (1000 rows)

# Step 2 — Train and save the model
python model.py
# → creates model.pkl + encoder.pkl

# Step 3 — Start the API server
uvicorn main:app --reload --port 8000
# API  → http://localhost:8000
# WS   → ws://localhost:8000/ws
# Health → http://localhost:8000/health
# Stats  → http://localhost:8000/stats
```

### 2. Frontend (new terminal)

```bash
cd echoad/frontend
npm install
npm run dev
# Dashboard → http://localhost:5173
```

---

## ML Model Details

- **Algorithm:** GradientBoostingClassifier (400 trees, learning rate 0.05)
- **Features:** 14 engineered features including:
  - Age buckets (18-24, 25-34, 35-44, 45-54, 55+)
  - Device × category interactions (`bid_x_mobile`, `highcat_x_top`, `mobile_x_highcat`)
  - One-hot encoded device, category, region, position
- **Target:** `click` (0 = no click, 1 = click)
- **Class imbalance handling:** sqrt-scaled sample weights (~1.64x for click class)
- **Threshold tuning:** Optimised for F1 with minimum 40% precision floor
- **Performance:** AUC ~0.69 (5-fold CV, std 0.03), Accuracy ~73%

### Value Tiers (as per brief)
| Tier | CTR Score | Dashboard |
|---|---|---|
| High Value | > 0.70 | 🟢 Green row |
| Average | 0.30 – 0.70 | ⚪ Default |
| Low Value | < 0.30 | 🔴 Red row |

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/ws` | WebSocket | Live ad stream (JSON per ad) |
| `/health` | GET | Server health check |
| `/stats` | GET | Total ads, high-value count, error rate, RPM |

---

## Dashboard Features

- **Live Feed Table** — scrolling ad list, color-coded by CTR tier, per-tier filters
- **CTR Trend Chart** — recharts line chart, last 20 scores
- **Heatmap** — category × device click distribution
- **Metrics Cards** — total ads processed, high/low value counts, avg CTR
- **Velocity Gauge** — real-time bids per minute
- **Toast Alerts** — pop-up notifications for high-value bids (score > 0.85)
- **Auto-reconnect** — exponential backoff on WebSocket disconnect
- **Demo Mode** — local ad generation if backend is offline (for UI demos)

---

## Notes

- Dataset is synthetic — regenerate anytime via `python generate_data.py`
- No database required — pure in-memory streaming pipeline
- Model performance varies slightly per run due to random data generation (no fixed seed in `generate_data.py`)
- With 1000 training rows, CV std of ~0.03 is expected and normal