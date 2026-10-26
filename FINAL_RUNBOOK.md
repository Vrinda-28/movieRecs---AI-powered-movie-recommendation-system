# Final System Runbook: Step-by-Step Operator Guide

This runbook contains exact, copy-pasteable instructions for running, operating, seeding, training, evaluating, and testing the system from a clean checkout.

---

## 1. Prerequisites

- **Docker & Docker Compose** (v24+)
- **Python 3.12** (for local development, CLI evaluation, and testing)
- **Node.js 20+ & npm 10+** (for frontend development)
- **Git**

---

## 2. Environment Setup

```bash
# 1. Clone the repository
git clone <repo-url> full-stack-recommendation-system
cd full-stack-recommendation-system

# 2. Configure environment variables
cp .env.example .env

# Verify that .env has appropriate credentials (defaults work out-of-the-box for local docker)
```

---

## 3. Starting the Backend Services (Docker Compose)

```bash
# Start PostgreSQL, Redis, FastAPI backend, Celery worker, and Celery beat
docker compose up --build -d

# Verify all containers are healthy
docker compose ps
```

Services exposed:
- **FastAPI Backend:** `http://localhost:8000` (Swagger docs at `http://localhost:8000/docs`)
- **PostgreSQL Database:** `localhost:5432` (Database: `recommenderdb`, User: `admin`, Password: `adminpassword`)
- **Redis Broker:** `localhost:6379`
- **PgAdmin:** `http://localhost:5050` (Email: `admin@admin.com`, Password: `admin`)

---

## 4. Database Seeding

### Fast Demo Seeding (Default 200 Users, ~11,000 Ratings)
```bash
# Seeding the fast demo dataset inside container or locally:
docker compose exec app python scripts/seed_db.py --users 200

# Or locally:
python scripts/seed_db.py --users 200
```

### Full MovieLens 1M Seeding (6,040 Users, 1,000,209 Ratings)
```bash
docker compose exec app python scripts/seed_db.py --full
```

---

## 5. Model Training

### Option A: Train via Admin Dashboard
1. Log into the web application as an administrator.
2. Navigate to the **Admin** panel (`/admin`).
3. Click **Retrain Model**. The live status will update (`queued` $\to$ `running` $\to$ `successful`).

### Option B: Train via Command Line
```bash
# Train on current database interactions:
docker compose exec app python -m app.services.recommender.train --epochs 10 --batch-size 256 --lr 0.001 --mask-zero --padding right

# Or run locally:
python -m app.services.recommender.train --epochs 10 --batch-size 256 --lr 0.001 --mask-zero --padding right
```
The model will be atomically verified, saved to `models_store/gru4rec_model.keras`, and archived with its sidecar metadata in `models_store/versions/`.

---

## 6. Starting the Frontend UI

```bash
# Navigate to frontend directory
cd recommendation-frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## 7. User Journeys & Verification Steps

### Step 7.1: Create an Admin Account
```bash
# Create an initial administrator account:
docker compose exec app python scripts/create_admin.py --email admin@example.com --password AdminPassword123!
```

### Step 7.2: Register a Regular User & Onboarding
1. Open `http://localhost:5173` and click **Register**.
2. Enter email (e.g. `user1@example.com`) and password.
3. You will be redirected to `/onboarding`.
4. Rate 3 or more movies across genres (e.g. *Toy Story* 5★, *Jurassic Park* 4★, *The Matrix* 5★).
5. Click **Finish Onboarding & View Recommendations**.

### Step 7.3: Explore Recommendations & Explanations
1. Open the **Recommendations** page (`/recommendations`).
2. Notice the personalized recommendations banner:
   - Items with source `"gru4rec"` carry the **Personalized** badge.
   - Explanation chips explain: `"Because you rated Toy Story (1995) highly"` or `"Shares genres (Sci-Fi, Action) with movies you rated highly"`.
3. Open any movie detail page (`/movies/:id`):
   - Submit ratings (updates in-place).
   - Write a text review.
   - Click **Save to Watchlist** (instantly synced).

---

## 8. Poster Enrichment (TMDB Integration)

To enrich movie metadata with real high-resolution posters from TMDB:
```bash
# Provide your TMDB API Key in .env (TMDB_API_KEY=your_key) and run:
python -m scripts.enrich_posters --limit 500
```
Missing or invalid posters automatically render high-contrast fallback cards with zero layout shifts.

---

## 9. Running Offline Leak-Free Evaluation CLI

Run the multi-seed, leak-free leave-last-out evaluation harness:
```bash
# Evaluate across 3 seeds on held-out user interactions:
python -m app.services.recommender.evaluate --leak-free --k 5 10 20 --seeds 42 43 44
```
Results, sample sizes, and 95% bootstrap confidence intervals are output to the terminal and persisted to:
- `models_store/evaluation/<timestamp>.json`
- `models_store/evaluation/<timestamp>.csv`

### Running the Diversity & Fairness Benchmark
```bash
python scripts/evaluate_diversity.py
```
Computes Catalogue Coverage, Top-10% Popularity Concentration, Gini Index, Shannon Entropy, and Intra-List Diversity (ILD).

---

## 10. Model Rollback & Version Recovery

To roll back the production model to a previous verified version:
```bash
# View available versions:
ls -la models_store/versions/

# Rollback via Python:
python -c "from app.services.recommender.train import rollback_model_version; print(rollback_model_version('gru4rec_<version_id>.keras'))"
```
Or use the one-click **Rollback to this** button on the `/admin` dashboard.

---

## 11. Automated Test Execution

```bash
# Run all 44 unit, integration, and system tests with coverage:
pytest tests/ -v --cov=app

# Run only unit tests:
pytest tests/test_unit.py -v

# Run only integration tests:
pytest tests/test_integration.py -v

# Run only system tests:
pytest tests/test_system.py -v

# Run frontend build & linting:
cd recommendation-frontend
npm run lint
npm run build
```
