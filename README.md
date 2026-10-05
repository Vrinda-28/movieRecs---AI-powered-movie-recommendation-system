<a name="readme-top"></a>

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <h2 align="center">AI-Powered Personalized Recommendation & Discovery System</h2>
  <p align="center">
    <strong>Shah & Anchor Kutchhi Engineering College — Computer Engineering — AY 2026–2027</strong><br />
    Team: <em>Vrinda Garg, Srushti Dedaniya, Nihaar Kotak</em><br />
    Base Repository Reference: <code>george-mountain/full-stack-recommendation-system</code> (MIT Licence), extended by the team.
  </p>
  <p align="center">
    A full-stack, sequential learning-based recommendation platform with GRU4Rec, FastAPI, PostgreSQL, Celery, Redis, and React.
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
    <li><a href="#extensions-beyond-the-base-repository">Extensions Beyond the Base Repository</a></li>
    <li><a href="#system-architecture">System Architecture</a></li>
    <li><a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#quick-start-with-docker-compose">Quick Start with Docker Compose</a></li>
        <li><a href="#database-seeding">Database Seeding</a></li>
        <li><a href="#frontend-setup">Frontend Setup</a></li>
      </ul>
    </li>
    <li><a href="#running-automated-tests">Running Automated Tests</a></li>
    <li><a href="#offline-evaluation--metrics">Offline Evaluation & Metrics</a></li>
    <li><a href="#project-structure">Project Structure</a></li>
    <li><a href="#api-endpoints-summary">API Endpoints Summary</a></li>
    <li><a href="#sdg-alignment">SDG Alignment</a></li>
    <li><a href="#license--attribution">License & Attribution</a></li>
  </ol>
</details>

---

## About The Project

This project provides an AI-driven personalized recommendation and discovery system that models user interaction sequences to predict next-item preferences using a **GRU4Rec** recurrent neural network architecture.

### Key Capabilities
- **Sequential Recommendation Engine**: GRU4Rec query-candidate dual tower architecture with Gated Recurrent Units capturing evolving temporal user taste.
- **Cold-Start Fallback**: Dynamic popularity fallback delivering top-ranked discoveries for new users with no prior interactions.
- **Role-Based Admin Authorization**: Enforced server-side permissions (`is_admin`) protecting movie management and retraining triggers.
- **Duplicate Rating In-Place Update**: Transparently updates ratings and timestamps when users re-rate movies.
- **Atomic Model Retraining**: Crash-safe, atomic model serialization ensuring uninterrupted API inference.
- **Background Retraining**: Celery Beat scheduled at midnight (`Asia/Kolkata`) backed by Redis.
- **Interactive UI**: Responsive dark-themed React frontend with real-time feedback, distinct personalized vs. popularity badges, and star rating controls.

---

## Extensions Beyond the Base Repository

This codebase substantially extends the reference architecture to address architectural gaps, security hardening, and rigorous evaluation:

| # | Extension / Feature | Implementation Details |
|---|---|---|
| 1 | **Role-Based Admin Authorization** | Added `is_admin` Boolean column to `User` DB model, created `get_current_admin_user` dependency raising HTTP 403 for unauthorized users, protected `POST /api/v1/movies/` and `POST /api/v1/admin/trigger-retrain-model`. |
| 2 | **Movie Deletion REST API** | Implemented `DELETE /api/v1/movies/{movie_id}` wired to `crud.movie.remove()`, replacing the previous simulated frontend stub with real database deletion and confirmation modal. |
| 3 | **Duplicate Rating Update-In-Place** | Enhanced `POST /api/v1/ratings/` and `CRUDBase.update` to update existing user ratings in place rather than generating duplicate rows. |
| 4 | **Rating Schema Validation** | Enforced `ge=1.0, le=5.0` validation constraints on `RatingBase.rating` in Pydantic schema (returning HTTP 422 for invalid ratings). |
| 5 | **Cold-Start Popularity Fallback** | Added `CRUDMovie.get_most_popular()` and fallback routing in `predict.py` when history is empty or model unavailable, returning `is_personalized: false` flag. |
| 6 | **Frontend Personalization Badge** | Enhanced `RecommendationsPage.jsx` to visually differentiate personalized GRU4Rec picks from cold-start popularity fallbacks. |
| 7 | **Crash-Safe Atomic Model Replacement** | Implemented atomic `os.replace` from a `.tmp` file in `train.py` preventing live model corruption if training encounters exceptions. |
| 8 | **Configurable Retrieval Window** | Configured `BruteForceRetrieval(k=50)` so `predict.py` can filter already-rated items and reliably fulfill requested `count` query parameters. |
| 9 | **Offline Evaluation Pipeline** | Created `app/services/recommender/evaluate.py` implementing a leak-free chronological leave-last-out protocol calculating Precision@K, Recall@K, Hit Rate@K, and NDCG@K against a Popularity baseline. |
| 10 | **Automated Test Suite (`pytest`)** | Added 22 unit, integration, and system tests under `tests/` mirroring Stage 2 test IDs (`UT-01` to `UT-08`, `IT-01` to `IT-08`, `ST-01` to `ST-06`). |
| 11 | **Security & CORS Hardening** | Restricted CORS in `main.py` from wildcard `*` to configurable origins (`settings.CORS_ORIGINS`) and secured `SECRET_KEY` handling. |
| 12 | **User-Scoped Endpoint Restrictions** | Restricted `/ratings/user/{user_id}` and `/recommendations/user/{user_id}` to self or verified admin users. |

---

## System Architecture

```
                                  +-----------------------------+
                                  |   React Frontend (Vite)     |
                                  |   http://localhost:5173     |
                                  +--------------+--------------+
                                                 | HTTP / JSON (JWT)
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
|    PostgreSQL Database      |   |    Recommender Service      |   |     Redis Broker / Queue    |
|    Users, Movies, Ratings   |   |    GRU4Rec / Fallback Engine|   |     Port 6379               |
+-----------------------------+   +--------------+--------------+   +--------------+--------------+
                                                 |                                 |
                                                 v                                 v
                                  +-----------------------------+   +-----------------------------+
                                  |      models_store/          |   |   Celery Worker & Beat      |
                                  |   gru4rec_model.keras       |<--|   Scheduled Retraining      |
                                  +-----------------------------+   +-----------------------------+
```

---

## Getting Started

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- [Node.js](https://nodejs.org/) (v18+) & npm
- Python 3.10+ (for local CLI / test execution)

### Quick Start with Docker Compose

1. **Clone and Configure Environment**:
   ```bash
   cp .env.example .env
   ```

2. **Launch All Services**:
   ```bash
   docker compose up --build -d
   ```
   This initializes six services:
   - `db` (PostgreSQL 15 on port 5432)
   - `pgadmin` (pgAdmin 4 on port 5050)
   - `redis` (Redis 7 on port 6379)
   - `app` (FastAPI backend on port 8000)
   - `worker` (Celery background worker)
   - `beat` (Celery Beat task scheduler)

3. **Check Service Health**:
   ```bash
   docker compose ps
   ```

### Database Seeding

Populate the database with the MovieLens-1M dataset:
```bash
docker compose exec app python /app/scripts/seed_db.py
```
*Note: The script downloads `ml-1m.zip`, loads movies, creates users, and inserts ratings with original timestamps.*

### Frontend Setup

In a separate terminal:
```bash
cd recommendation-frontend
npm install
npm run dev
```
Open **http://localhost:5173** in your browser.

---

## Running Automated Tests

The test suite contains Unit (`UT`), Integration (`IT`), and System (`ST`) tests in accordance with Stage 2 Report specifications.

### Run via Docker
```bash
docker compose exec app pytest tests/ -vv --cov=app
```

### Run Locally
```bash
pip install -r requirements.txt
pytest tests/ -vv
```

### Test Coverage Summary:
- **Unit Tests (`UT-01` to `UT-08`)**: Chronological sort, window padding, vocabulary handling, bcrypt password hashing, expired token rejection, rating schema validation (1-5), Stage 2 toy example arithmetic reproduction, already-rated item masking.
- **Integration Tests (`IT-01` to `IT-08`)**: User registration and login, duplicate user rejection (400), rating creation with timestamps, in-place rating updates, active-user recommendations, cold-start popularity fallback (200), admin-only endpoint protection (403), atomic model file replacement.
- **System Tests (`ST-01` to `ST-06`)**: End-to-end user journey, health check, bad login error handling, token expiration redirect, recommendation response latency (< 1s), recommendation consistency.

---

## Offline Evaluation & Metrics

The evaluation module implements a leak-free **Chronological Leave-Last-Out** protocol:
- For every user with $\ge 3$ interactions, the chronologically last rating is held out as the test target.
- The earlier sequence is fed to the GRU4Rec model and the Popularity Baseline.
- Precision@K, Recall@K, HitRate@K, and NDCG@K are computed for $K \in \{5, 10, 20\}$.

### Run Evaluation
```bash
docker compose exec app python -m app.services.recommender.evaluate
```
Output results are written to:
- `evaluation_output/evaluation_results.json`
- `evaluation_output/evaluation_results.csv`

---

## Project Structure

```
full-stack-recommendation-system-main/
├── app/
│   ├── main.py                       # FastAPI application & CORS setup
│   ├── security.py                   # Password hashing (bcrypt) & JWT helpers
│   ├── core/
│   │   └── config.py                 # Application settings & environment variables
│   ├── db/
│   │   ├── base_class.py             # SQLAlchemy Declarative Base
│   │   ├── models.py                 # ORM models (User, Movie, Rating) with is_admin
│   │   ├── session.py                # Async database engine & session creation
│   │   └── crud.py                   # CRUD operations (User, Movie, Rating, Popularity)
│   ├── schemas/                      # Pydantic v2 validation models
│   │   ├── user.py                   # User schemas with is_admin
│   │   ├── movie.py                  # Movie schemas
│   │   ├── rating.py                 # Rating schemas with ge=1, le=5 validation
│   │   └── token.py                  # JWT token schemas
│   ├── api/
│   │   ├── deps.py                   # Auth dependencies & get_current_admin_user
│   │   └── v1/
│   │       ├── api.py                # API router aggregation
│   │       └── endpoints/
│   │           ├── users.py          # Registration, login, /users/me
│   │           ├── movies.py         # Catalogue browse, search, POST/DELETE (Admin)
│   │           ├── ratings.py        # Rating submission & update in place
│   │           ├── recommendations.py# User recommendations & fallback routing
│   │           └── admin.py          # Model retraining & Celery trigger endpoints
│   ├── services/recommender/
│   │   ├── model.py                  # GRU4Rec SequentialRetrievalModel definition
│   │   ├── preprocessing.py          # Sequence building, padding, prediction context
│   │   ├── train.py                  # Atomic model training script
│   │   ├── predict.py                # Inference & cold-start fallback handler
│   │   └── evaluate.py               # Leave-last-out evaluation pipeline
│   └── worker/
│       ├── celery_app.py             # Celery instance & beat schedule
│       └── tasks.py                  # Celery retraining & test tasks
├── recommendation-frontend/          # React + Vite frontend application
│   ├── src/
│   │   ├── contexts/                 # AuthContext (real is_admin) & AppContext
│   │   ├── services/ApiService.js    # Centralized HTTP client
│   │   ├── pages/                    # HomePage, MovieDetailPage, RecommendationsPage
│   │   └── components/               # AdminPage, MovieCard, RatingModal, StarRatingInput
│   └── package.json
├── tests/                            # Automated test suite
│   ├── conftest.py                   # Pytest fixtures & async SQLite setup
│   ├── test_unit.py                  # UT-01 to UT-08
│   ├── test_integration.py           # IT-01 to IT-08
│   └── test_system.py                # ST-01 to ST-06
├── scripts/
│   └── seed_db.py                    # MovieLens-1M dataset download and DB seeding
├── models_store/                     # Trained model storage (gru4rec_model.keras)
├── Dockerfile                        # Backend image definition (python:3.10-slim)
├── docker-compose.yml                # Multi-container service definitions
├── Makefile                          # Helper build, format, test targets
├── requirements.txt                  # Python dependencies
└── README.md                         # Documentation
```

---

## API Endpoints Summary

| Method | Path | Description | Access |
|---|---|---|---|
| `POST` | `/api/v1/users/register` | Register new account | Public |
| `POST` | `/api/v1/users/login/token` | Login to receive JWT token | Public |
| `GET` | `/api/v1/users/me` | Fetch current user profile & `is_admin` | Authenticated |
| `GET` | `/api/v1/movies/` | Browse & search movie catalogue | Public |
| `GET` | `/api/v1/movies/{id}` | Get movie detail by ID | Public |
| `POST` | `/api/v1/movies/` | Create a new movie | **Admin only** |
| `DELETE` | `/api/v1/movies/{id}` | Delete a movie | **Admin only** |
| `POST` | `/api/v1/ratings/` | Submit/update movie rating (1.0-5.0) | Authenticated |
| `GET` | `/api/v1/ratings/user/me` | Get current user's rating history | Authenticated |
| `GET` | `/api/v1/ratings/user/{id}` | Get specific user's ratings | Self or Admin |
| `GET` | `/api/v1/recommendations/user/me` | Get personalized / fallback recommendations | Authenticated |
| `GET` | `/api/v1/recommendations/user/{id}` | Get recommendations for user | Self or Admin |
| `POST` | `/api/v1/admin/trigger-retrain-model` | Trigger background model retraining | **Admin only** |
| `GET` | `/health` | Service health status | Public |

---

## SDG Alignment

- **SDG 9: Industry, Innovation, and Infrastructure**:
  - Implements research-level sequential machine learning (GRU4Rec) within a production-ready, modular architecture.
  - Promotes lightweight, reproducible, containerized open-source ML infrastructure.
- **Data Minimization & Responsible AI**:
  - Stores only necessary interaction sequences without tracking sensitive personal information.
  - Transparently flags cold-start discoveries vs. personalized recommendations.

---

## License & Attribution

Distributed under the **MIT License**. See [`LICENSE.txt`](LICENSE.txt) for details.

This project extends the open-source reference project:
- Base Repository: [george-mountain/full-stack-recommendation-system](https://github.com/george-mountain/full-stack-recommendation-system)
- Extended & Evaluated by: **Vrinda Garg, Srushti Dedaniya, Nihaar Kotak** (Shah & Anchor Kutchhi Engineering College).
