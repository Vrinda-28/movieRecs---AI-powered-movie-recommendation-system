<<<<<<< HEAD
<a name="readme-top"></a>

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <h2 align="center">AI-Powered Personalized Recommendation & Discovery System</h2>
  <p align="center">
    <strong>Shah & Anchor Kutchhi Engineering College — Computer Engineering — AY 2026–2027</strong><br />
    Team: <em>Vrinda Garg, Srushti Dedaniya, Nihaar Kotak</em><br />
    Base Repository Reference: <code>george-mountain/full-stack-recommendation-system</code> (MIT Licence), significantly extended by the team.
  </p>
  <p align="center">
    A production-grade, sequential learning-based recommendation platform with GRU4Rec, FastAPI, PostgreSQL, Celery, Redis, and React.
    <br />
    <a href="http://127.0.0.1:8000/docs"><strong>Explore Swagger API Docs »</strong></a>
    ·
    <a href="http://localhost:5173/">View React Frontend</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a></li>
    <li><a href="#key-academic-contributions">Key Academic Contributions</a></li>
    <li><a href="#system-architecture">System Architecture</a></li>
    <li><a href="#machine-learning-pipeline">Machine Learning Pipeline (GRU4Rec)</a></li>
    <li><a href="#empirical-benchmark-results">Empirical Benchmark Results</a></li>
    <li><a href="#getting-started">Getting Started</a></li>
    <li><a href="#running-automated-tests">Running Automated Tests</a></li>
    <li><a href="#documentation-index">Documentation Index</a></li>
    <li><a href="#license--attribution">License & Attribution</a></li>
  </ol>
</details>

---

## About The Project

This project implements a full-stack, AI-driven sequential recommendation platform that predicts dynamic user preferences using **GRU4Rec** recurrent neural networks on the MovieLens 1M dataset.

### Core Architectural Flow
```
USER INTERACTIONS ──► SEQUENTIAL CHRONOLOGICAL CONTEXT ──► GRU4Rec ──► CANDIDATE RETRIEVAL ──► RATED FILTERING ──► TOP-K RANKING & EXPLANATION
```

---

## Key Academic Contributions

1. **Two-Tower Sequential Architecture:** Dual-tower model with zero-masking (`mask_zero=True`) in the query GRU tower and candidate embeddings, optimized via in-batch matrix factorization.
2. **Leak-Free Chronological Evaluation:** Strict leave-last-out evaluation harness holding out the final qualifying interaction ($t_{\max}$) per user, evaluated with **95% Bootstrap Confidence Intervals** against an un-leaked popularity baseline across 3 seeds (`[42, 43, 44]`).
3. **Model-Derived Honest Explanations:** Explanations derived from candidate embedding cosine similarities (`"Because you rated <Movie> highly"` for $\text{Sim} \ge 0.40$), genre intersections, or clear popularity labels without LLM hallucination.
4. **Diversity & Fairness Measurement:** Rigorous measurement of Catalogue Coverage (53.4%), Popularity Concentration (13.0% in Top 10%), Gini Index (0.7154), Shannon Entropy (10.49 bits), and Intra-List Diversity (ILD).
5. **Production Safety & Archival:** Atomic model deployment with forward-pass verification gates, automated sidecar JSON lineage (`*.keras.json`), and one-click rollback capabilities.
6. **Full-Stack Cinematic UI:** Responsive React 19 interface with hero billboarding, star ratings, paginated reviews, watchlist management, and an administrative control plane.

---

## System Architecture

```
                                  +-----------------------------+
                                  |   React Frontend (Vite)     |
                                  |   http://localhost:5173     |
                                  +--------------+--------------+
                                                 | HTTP / JSON (Bearer JWT)
                                                 v
                                  +-----------------------------+
                                  |     FastAPI REST API        |
                                  |     http://127.0.0.1:8000   |
                                  +---+----------+----------+---+
                                      |          |          |
                   +------------------+          |          +------------------+
                   |                             |                             |
                   v                             v                             v
+-----------------------------+   +-----------------------------+   +-----------------------------+
|    PostgreSQL 15 Database   |   |   Redis 7 (Message Broker)  |   |   Sequential GRU4Rec Model  |
|  - users, movies, ratings   |   +--------------+--------------+   |  - Query GRU Tower (32-d)   |
|  - reviews, watchlist, log  |                  |                  |  - Candidate Embedding (32) |
+-----------------------------+                  v                  |  - BruteForceRetrieval (k=50|
                                  +-----------------------------+   +-----------------------------+
                                  |    Celery Background Worker |
                                  |  - Model Retraining Task    |
                                  |  - Verification Gate        |
                                  +-----------------------------+
```

---

## Machine Learning Pipeline (GRU4Rec)

### Training vs. Inference Distinction
- **Training Time:** User interaction histories are sliced into sliding windows of length $L=10$ with padding mode right. In-batch negative sampling trains query and candidate representations simultaneously via cross-entropy loss with early stopping on validation loss.
- **Inference Time:** When a user requests recommendations, the system retrieves their most recent ratings ordered chronologically (oldest $\to$ newest), truncates to the last 10 interactions, formats a shape `(1, 10)` tensor, executes vector retrieval against all 3,952 movie candidates, filters already-rated titles, and returns the Top-K items with explanation reasons.

---

## Empirical Benchmark Results

*Measured on 1,000 leave-last-out test users across seeds `[42, 43, 44]` on MovieLens 1M (161,907 training sequences):*

| Metric ($K=10$) | GRU4Rec Sequential Model | Popularity Baseline | Relative Gain | 95% Bootstrap Confidence Interval |
| :--- | :--- | :--- | :--- | :--- |
| **Hit Rate@5** | **8.50%** | 2.00% | **+325% (+4.25x)** | N/A |
| **Hit Rate@10** | **13.43%** | 3.70% | **+263% (+3.63x)** | **[11.80%, 15.80%]** (Pop: [2.60%, 4.90%]) |
| **Hit Rate@20** | **20.07%** | 6.10% | **+229% (+3.29x)** | N/A |
| **NDCG@10** | **0.0682** | 0.0188 | **+263% (+3.63x)** | **[0.0608, 0.0842]** (Pop: [0.0126, 0.0257]) |
| **Catalogue Coverage** | **76.55%** (3,025 movies) | 5.04% (199 movies) | **15.2x Catalogue Reach** | Sourced from long-tail personalization |
| **Inference Latency** | **0.02 ms / user** | 0.01 ms / user | Negligible | Vector dot product |

---

## Getting Started

### Quick Start with Docker Compose
```bash
# 1. Clone & Configure
git clone <repo-url>
cd full-stack-recommendation-system
cp .env.example .env

# 2. Start all backend services
docker compose up --build -d

# 3. Seed demo dataset (200 users, ~11k ratings)
docker compose exec app python scripts/seed_db.py --users 200

# 4. Start React Frontend
cd recommendation-frontend
npm install
npm run dev
```
Open `http://localhost:5173` to interact with the system.

---

## AI Features (Groq)

The platform integrates Groq (`llama-3.3-70b-versatile` or custom configured Groq model) via the official `groq` SDK (`AsyncGroq`) to provide two strictly grounded discovery features without modifying the core GRU4Rec sequential recommender:

1. **Natural-Language Movie Discovery (`POST /api/v1/ai/discover`):** Translates free-form requests into structured search preferences, resolves mentioned reference titles deterministically against catalogue data, filters out excluded genres token-exactly, and computes an explainable relevance score with human-readable rationale.
2. **Grounded Movie Q&A — "Ask About Movies" (`POST /api/v1/ai/ask`):** An interactive assistant grounded in factual catalogue attributes (title, parsed release year, genres, community ratings) and deterministic candidate titles.

> **Honesty & Grounding Invariant:** The database contains only `title`, `year`, `genres`, and `ratings`. It contains **no** plot summaries, directors, cast lists, runtimes, streaming availability, age ratings, or graphic violence content warnings. The AI assistant explicitly marks these attributes as **unverifiable from catalogue data** rather than fabricating answers.

### Local Setup Instructions

```bash
# 1. Create a key at Groq Console (https://console.groq.com)
# 2. Add to your repo-root .env (this file is git-ignored):
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TIMEOUT_SECONDS=20

# 3. Rebuild so the new dependency installs:
docker compose up --build -d     # or non-docker: pip install -r requirements.txt

# 4. Open http://localhost:5173 and log in to use AI discovery.
# (Windows PowerShell for a non-Docker run): $env:GROQ_API_KEY="your_key"
```

### Endpoints & Usage

* **`GET /api/v1/ai/status`** (Public)
  Returns configuration status without exposing API keys:
  ```bash
  curl -s http://127.0.0.1:8000/api/v1/ai/status
  # Response: {"enabled": true, "model": "llama-3.3-70b-versatile"}
  ```

* **`POST /api/v1/ai/discover`** (Authenticated)
  Natural-language discovery:
  ```bash
  curl -s -X POST http://127.0.0.1:8000/api/v1/ai/discover \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "mind-bending sci-fi with an emotional story, similar to The Matrix, no horror, 90s"}'
  ```

* **`POST /api/v1/ai/ask`** (Authenticated)
  Grounded movie Q&A:
  ```bash
  curl -s -X POST http://127.0.0.1:8000/api/v1/ai/ask \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"question": "Recommend three similar movies from our catalogue", "movie_id": 2, "history": []}'
  ```

### Safety, Cost, and Architecture Controls
* **In-process Sliding-Window Rate Limiting:** Configurable via `AI_RATE_LIMIT_PER_MIN` (default 10 requests/min/user), returning HTTP 429 with `Retry-After`.
* **Interpretation Caching:** 10-minute in-memory TTL cache (max 256 entries) for discovery prompts to avoid redundant API calls. Never caches across user profiles.
* **Strict Privacy:** User prompts and API keys are never logged at INFO level. API keys are redacted from all error messages and responses.
* **Free-Tier Data Note:** When using Google AI Studio free tier keys, Google may use prompt inputs to improve its products; avoid submitting personal data.
* **Catalogue Boundaries:** MovieLens 1M titles span 1919–2000. Post-2000 reference films (e.g. *Interstellar (2014)*) are truthfully reported as `unresolved_references` rather than hallucinatory matches.
* **Model Knowledge Toggle:** By default, `ASK_ALLOW_MODEL_KNOWLEDGE=False` enforces strict catalogue grounding. Setting it to `True` permits general knowledge plot synopses explicitly labelled as unverified.


---

## Running Automated Tests

```bash
# Run all 44 unit, integration, and system tests:
pytest tests/ -v --cov=app

# Run offline evaluation CLI:
python -m app.services.recommender.evaluate --leak-free --k 5 10 20 --seeds 42 43 44

# Run diversity evaluation:
python scripts/evaluate_diversity.py
```

---

## Documentation Index

- [**FINAL_SYSTEM_MAP.md**](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/FINAL_SYSTEM_MAP.md): Full architectural diagrams, database tables, API routes, and file mappings.
- [**FINAL_RUNBOOK.md**](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/FINAL_RUNBOOK.md): Complete step-by-step operator and setup manual.
- [**REPORT_FACTS.md**](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/REPORT_FACTS.md): Authoritative measured facts and experimental tables for the academic report.

---

## License & Attribution

- **License:** MIT License.
- **Academic Attribution:** Developed at Shah & Anchor Kutchhi Engineering College (AY 2026–2027) by *Vrinda Garg, Srushti Dedaniya, and Nihaar Kotak*.
- **Base Architecture Reference:** `george-mountain/full-stack-recommendation-system` (MIT License).
=======
# movieRecs---AI-powered-movie-recommendation-system
>>>>>>> origin/main
