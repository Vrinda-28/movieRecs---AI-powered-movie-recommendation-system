# Report Facts: Verified Empirical Data & Academic Reference

This document contains **strictly measured facts, empirical benchmark outputs, and concrete parameters** for direct inclusion in the Stage 2 / Stage 3 Academic Project Report. Every figure is traceable to a specific artifact or command.

---

## 1. System & Service Inventory

| Component | Technology | Role in System | Port / Resource |
| :--- | :--- | :--- | :--- |
| **API Application** | FastAPI 0.115+ (Python 3.12) | Asynchronous REST endpoints, JWT auth, validation, prediction pipeline | `:8000` |
| **Database** | PostgreSQL 15 | Persistent relational storage for users, movies, ratings, reviews, watchlist | `:5432` |
| **Broker & State** | Redis 7 (Alpine) | Message queue broker for Celery and task state backend | `:6379` |
| **Background Worker** | Celery 5.4+ (Solo pool) | Asynchronous model retraining, verification gate, version archiving | Worker container |
| **Periodic Scheduler** | Celery Beat 5.4+ | Scheduled database maintenance and background retraining jobs | Beat container |
| **Frontend Client** | React 19 + Vite 6 + Tailwind CSS | Cinematic poster discovery UI, star ratings, reviews, administration | `:5173` |
| **Deep Learning Engine**| TensorFlow 2.16+ / Keras 3.8+ | Sequential GRU4Rec retrieval and embedding vector calculations | `models_store/` |

---

## 2. Dataset Counts & Ground Truth

*Measured using `scripts/seed_db.py` and `scripts/run_experiments.py` on the MovieLens 1M dataset (`data/ml-1m/`):*

| Metric / Entity | Shipped Fast Demo Subset | Full MovieLens 1M Benchmark Set |
| :--- | :--- | :--- |
| **Total Users** | 200 | 6,040 |
| **Total Movies in Catalogue** | 3,952 (Internal vocab 1..3,952) | 3,952 (Internal vocab 1..3,952) |
| **Total Ratings Recorded** | 11,002 | 1,000,209 |
| **Eligible Evaluated Users ($\ge 5$ interactions)** | 200 users | 1,000 evaluation users |
| **Training Sequence Examples** | 10,602 sliding-window sequences | 161,907 sliding-window sequences |
| **Ratings Filter Threshold** | Rating $\ge 3.0$ (Positive feedback signal) | Rating $\ge 3.0$ (Positive feedback signal) |

---

## 3. Shipped Model Hyperparameters (Sidecar Lineage)

*Extracted directly from live sidecar JSON (`models_store/gru4rec_model.keras.json`):*

- **Model Architecture:** `SequentialRetrievalModel` (Two-Tower GRU4Rec)
- **Embedding Dimension ($d$):** `32`
- **GRU Hidden Units:** `32`
- **Context Window Length ($L$):** `10`
- **Vocabulary Size ($V$):** `3,953` (Movie IDs 1..3,952 + Reserved Index 0 for padding)
- **Zero-Masking (`mask_zero`):** `True`
- **Padding Mode:** `Right-padded with 0`
- **Loss Function:** `CategoricalCrossentropy(from_logits=True)` (In-Batch Softmax)
- **Optimizer:** `AdamW` (Learning Rate: `0.001`, Weight Decay: `1e-4`)
- **Batch Size:** `256`
- **Validation Strategy:** `10% Random Holdout` with `EarlyStopping(patience=3, restore_best_weights=True)`
- **Live Model File Size:** `~580 KB` (`.keras` archive)

---

## 4. Empirical Evaluation Benchmark (Leak-Free Chronological Leave-Last-Out)

*Benchmark output from `models_store/evaluation/experiments_summary.json` evaluated across 3 fixed random seeds `[42, 43, 44]` on 1,000 held-out test users (1,000 target interactions, 161,907 training sequences):*

| Metric ($K=10$) | GRU4Rec Sequential Model | Popularity Baseline | Relative Gain / Lift | 95% Bootstrap Confidence Interval |
| :--- | :--- | :--- | :--- | :--- |
| **Hit Rate@5** | **8.50%** | 2.00% | **+325% (+4.25x)** | N/A |
| **Hit Rate@10** | **13.43%** | 3.70% | **+263% (+3.63x)** | **[11.80%, 15.80%]** (Pop: [2.60%, 4.90%]) |
| **Hit Rate@20** | **20.07%** | 6.10% | **+229% (+3.29x)** | N/A |
| **NDCG@10** | **0.0682** | 0.0188 | **+263% (+3.63x)** | **[0.0608, 0.0842]** (Pop: [0.0126, 0.0257]) |
| **Precision@10**| **0.0134** | 0.0037 | **+262%** | N/A |
| **Recall@10** | **0.1343** | 0.0370 | **+263%** | N/A |
| **Catalogue Coverage** | **76.55%** (3,025 movies) | 5.04% (199 movies) | **15.2x Catalogue Reach** | Sourced from long-tail personalization |
| **Avg Inference Latency** | **0.02 ms / user** (Batched) | 0.01 ms / user | Negligible | Pure vector dot product |

---

## 5. Diversity & Fairness Measurement

*Empirical output from `scripts/evaluate_diversity.py` (`models_store/evaluation/diversity_summary.json`):*

| Diversity Dimension | GRU4Rec (Standard) | GRU4Rec + MMR ($\lambda=0.7$) | Popularity Baseline | Academic Finding |
| :--- | :--- | :--- | :--- | :--- |
| **Unique Items Recommended** | **2,110** | **2,107** | **132** | Model explores **16x more diverse catalogue items**. |
| **Catalogue Coverage** | **53.4%** | **53.3%** | **3.3%** | Over half the catalogue is actively recommended. |
| **Top-10% Pop Concentration** | **13.0%** | **13.2%** | **100.0%** | Popularity traps users in blockbusters; GRU4Rec personalizes niches. |
| **Gini Coefficient ($0 \to 1$)**| **0.7154** | **0.7151** | **0.9934** | Popularity acts as an extreme monopoly (0.9934). |
| **Shannon Entropy** | **10.49 bits** | **10.49 bits** | **5.11 bits** | $>2\times$ higher information entropy in recommendation distributions. |
| **Intra-List Diversity (ILD)** | **0.5907** | **0.5960** | **0.7555** | GRU4Rec recommendations are cohesive to the user's sequential taste cluster. |

---

## 6. Personal Fields Stored Per User

*Audited directly from SQLAlchemy model declarations in `app/db/models.py`:*

1. `users`: `id`, `email`, `hashed_password` (bcrypt), `is_active`, `is_admin`, `created_at`, `updated_at`.
2. `ratings`: `user_id`, `movie_id`, `rating` (float 1.0–5.0), `timestamp` (Unix seconds).
3. `reviews`: `user_id`, `movie_id`, `text` (String, max 2000 chars), `created_at`, `updated_at`.
4. `watchlist`: `user_id`, `movie_id`, `created_at`.
5. `interactions`: `user_id`, `movie_id`, `interaction_type` (`VIEW`, `CLICK`, `SEARCH`, `RATE`, `WATCHLIST_ADD`), `metadata_json`, `timestamp`.

*No personal data beyond email and interaction history is collected or stored.*

---

## 7. Quality Assurance & Test Verification

*Measured via `pytest tests/ -q --cov=app`:*

- **Total Automated Tests:** **44 / 44 Passing (100%)** in **13.28s**
- **Unit Tests (`test_unit.py`):** 19 tests (`UT-01` through `UT-19`)
- **Integration Tests (`test_integration.py`):** 19 tests (`IT-01` through `IT-19`)
- **System / Scenario Tests (`test_system.py`):** 6 tests (`ST-01` through `ST-06`)
- **Backend Code Coverage:** **55%** across all 2,135 application statements.
- **Frontend Build Validation:** `vite build` completed in **431ms** (0 errors).
- **Frontend Lint Validation:** `eslint .` passed with **0 errors**.

---

## 8. Documented Academic & Practical Limitations

1. **Cold-Start Sequence Length Requirement:** GRU4Rec requires a minimum sequence history ($\ge 3$ ratings) to compute expressive recurrent hidden states. For users with $<3$ interactions, the system falls back to popularity ranking.
2. **Post-Training New Movie Out-of-Vocabulary (OOV):** Newly inserted movies with database IDs $> V$ (where $V$ was the maximum vocabulary ceiling at training time) cannot be represented by the fixed embedding matrix until model retraining occurs. The inference pipeline safely skips OOV IDs.
3. **Retrieval Scores vs Predicted Star Ratings:** The BruteForce retrieval layer produces relative dot-product ranking scores rather than absolute star ratings ($1.0 - 5.0$) or calibrated click probabilities.
4. **Offline Evaluation vs Online A/B Testing:** Offline leave-last-out evaluation measures historical top-K accuracy on observed ratings, which may underestimate serendipitous discoveries that a user would enjoy but had not previously rated.
