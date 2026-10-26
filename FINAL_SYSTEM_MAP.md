# Final System Map & Architecture Reference

This document maps the complete full-stack sequential recommender system, tracing data flows from user actions to deep learning retrieval models, asynchronous workers, and cinematic user interfaces.

---

## 1. System Architecture & Topology

```mermaid
graph TD
    subgraph Frontend ["Client Layer (React 19 + Vite + Tailwind CSS)"]
        UI_Home["HomePage (/)\n- Hero Billboard\n- Personalized SectionRow\n- Trending Scroller\n- Genre Filter Grid"]
        UI_Movie["MovieDetailPage (/movies/:id)\n- Backdrop Hero\n- Accessible 1-5★ Rating\n- Paginated Reviews\n- Watchlist Toggle\n- Embedding-Similar / Genre Movies"]
        UI_Recs["RecommendationsPage (/recommendations)\n- Ranked AI Picks\n- Truthful Source Badges\n- RecommendationReason Chips"]
        UI_Onboard["OnboardingPage (/onboarding)\n- Cold-Start 5-Genre Grid\n- Immediate Personalization Transition"]
        UI_Admin["AdminPage (/admin)\n- Live System Diagnostics\n- Retraining Trigger & Status Polling\n- Version History & Rollback\n- Stored Evaluation Dashboard"]
        UI_Profile["ProfilePage (/profile)\n- Chronological Rating History\n- Watchlist Summary\n- Interactions Log"]
    end

    subgraph API ["Backend Application Layer (FastAPI)"]
        API_Auth["/api/v1/users\n- Register & Login (JWT)\n- Privilege Escalation Guard\n- User History & Personas"]
        API_Movies["/api/v1/movies\n- Catalogue Pagination & Search\n- Onboarding Diverse Selection\n- Poster Image Fallbacks"]
        API_Ratings["/api/v1/ratings\n- In-Place Upsert Rating\n- Chronological Timestamps"]
        API_Reviews["/api/v1/reviews\n- CRUD & Ownership Enforcement\n- Pagination & Aggregates"]
        API_Watchlist["/api/v1/watchlist\n- Idempotent Add / Remove\n- User Watchlist Retrieval"]
        API_Interactions["/api/v1/interactions\n- Implicit Log (VIEW, CLICK, SEARCH)"]
        API_Recs["/api/v1/recommendations\n- Sequential Context Windowing\n- GRU4Rec Model Inference\n- Cold-Start Popularity Fallback\n- Candidate Cosine Neighbor Explanations\n- Optional MMR Re-Ranking"]
        API_Admin["/api/v1/admin\n- System Health Diagnostics\n- SQL Database Counts\n- Model Lineage & Sidecars\n- Offline Benchmark Reader\n- Version Rollback Controller"]
    end

    subgraph Workers ["Asynchronous Execution Layer (Celery + Redis)"]
        Redis_Broker[("Redis 7 (Broker & State)")]
        Celery_Worker["Celery Worker\n- train_recommendation_model_task\n- Model Verification Gate\n- Atomic Deployment\n- Version Archival & Sidecar Generation"]
        Celery_Beat["Celery Beat\n- Periodic Scheduled Maintenance"]
    end

    subgraph ML ["Machine Learning Engine (TensorFlow / Keras 3)"]
        GRU_Model["SequentialRetrievalModel\n- Query Tower: Embedding(3953, 32, mask_zero=True) + GRU(32)\n- Candidate Tower: Embedding(3953, 32)\n- BruteForceRetrieval Layer (Top-50 candidates)"]
        Disk_Model[("models_store/gru4rec_model.keras\n+ Sidecar JSON Metadata\n+ models_store/versions/\n+ models_store/evaluation/")]
    end

    subgraph Storage ["Persistent Database Layer (PostgreSQL 15)"]
        DB[(PostgreSQL Database\n- users, movies, ratings\n- reviews, watchlist, interactions)]
    end

    Frontend -->|HTTP / JSON (Bearer Token)| API
    API -->|Async SQLAlchemy (asyncpg)| DB
    API -->|Enqueue Task / Query Status| Redis_Broker
    Redis_Broker --> Celery_Worker
    Celery_Worker -->|Train & Verify| GRU_Model
    Celery_Worker -->|Deploy Atomically| Disk_Model
    API -->|Load & Hot-Reload on mtime| Disk_Model
```

---

## 2. Database Schema

| Table Name | Primary Key | Foreign Keys | Indexed Columns | Description |
| :--- | :--- | :--- | :--- | :--- |
| `users` | `id` (Integer) | None | `email` (Unique) | User identity, hashed bcrypt password, `is_active`, `is_admin`, timestamps. |
| `movies` | `id` (Integer) | None | `movie_lens_id`, `title` | Internal movie catalogue, MovieLens ID, title, pipe-separated genres, poster URL. |
| `ratings` | `id` (Integer) | `user_id` $\to$ `users.id`<br>`movie_id` $\to$ `movies.id` | `user_id`, `movie_id`, `(user_id, movie_id)` (Unique) | User 1.0-5.0 star ratings with Unix epoch seconds timestamp. |
| `reviews` | `id` (Integer) | `user_id` $\to$ `users.id`<br>`movie_id` $\to$ `movies.id` | `user_id`, `movie_id`, `(user_id, movie_id)` (Unique) | User textual reviews (up to 2,000 chars) with update timestamps. |
| `watchlist` | `id` (Integer) | `user_id` $\to$ `users.id`<br>`movie_id` $\to$ `movies.id` | `user_id`, `movie_id`, `(user_id, movie_id)` (Unique) | Bookmarked movies saved for future viewing. |
| `interactions` | `id` (Integer) | `user_id` $\to$ `users.id`<br>`movie_id` $\to$ `movies.id` | `user_id`, `movie_id`, `interaction_type`, `timestamp` | Implicit user activity stream (`VIEW`, `CLICK`, `SEARCH`, `RATE`, `WATCHLIST_ADD`). |

---

## 3. Complete API Endpoint Directory

### Authentication & Users ([`app/api/v1/endpoints/users.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/api/v1/endpoints/users.py))
- `POST /api/v1/users/register`: Register new user. Explicitly rejects client privilege escalation (`is_admin=False`).
- `POST /api/v1/users/login/token`: OAuth2 password flow; returns JWT access token.
- `GET /api/v1/users/me`: Returns currently authenticated user profile.
- `GET /api/v1/users/me/history`: Unified chronological timeline of ratings and interactions.

### Catalogue & Discovery ([`app/api/v1/endpoints/movies.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/api/v1/endpoints/movies.py))
- `GET /api/v1/movies/`: Paginated movie list with title search and genre filters.
- `GET /api/v1/movies/onboarding`: Returns 15 genre-balanced, highly-rated movies across 5 diverse categories.
- `GET /api/v1/movies/{id}`: Detailed movie metadata, average rating, rating counts, and user reviews.
- `GET /api/v1/movies/{id}/similar`: Candidate-tower embedding cosine neighbors (`"Similar by viewing patterns"`) or genre fallback (`"More in <genre>"`).
- `POST /api/v1/movies/`: Admin only; create new catalogue entry.
- `DELETE /api/v1/movies/{id}`: Admin only; delete movie entry.

### Ratings ([`app/api/v1/endpoints/ratings.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/api/v1/endpoints/ratings.py))
- `POST /api/v1/ratings/`: Submit or update a 1.0–5.0 star rating in-place; logs `RATE` interaction.
- `GET /api/v1/ratings/user/me`: Fetch caller's ratings descending by timestamp.

### Reviews ([`app/api/v1/endpoints/reviews.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/api/v1/endpoints/reviews.py))
- `GET /api/v1/reviews/movies/{movie_id}`: Paginated list of user reviews.
- `POST /api/v1/reviews/`: Author review for a movie.
- `PUT /api/v1/reviews/{review_id}`: Edit own review. Enforces strict ownership.
- `DELETE /api/v1/reviews/{review_id}`: Delete own review. Enforces ownership or admin role.

### Watchlist ([`app/api/v1/endpoints/watchlist.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/api/v1/endpoints/watchlist.py))
- `POST /api/v1/watchlist/{movie_id}`: Idempotently add movie to caller's watchlist.
- `DELETE /api/v1/watchlist/{movie_id}`: Remove movie from watchlist.
- `GET /api/v1/watchlist/`: Retrieve paginated watchlist items with movie details.
- `GET /api/v1/watchlist/check/{movie_id}`: Returns `{ "in_watchlist": bool }`.

### Recommendations & Explanations ([`app/api/v1/endpoints/recommendations.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/api/v1/endpoints/recommendations.py))
- `GET /api/v1/recommendations/user/me`: Retrieves personalized Top-K recommendations with truthful source labels and model-derived explanation reasons.
- `GET /api/v1/recommendations/user/{user_id}`: Fetch recommendations for target user (Admin only).
- `GET /api/v1/recommendations/debug/me`: Admin-only audit trace showing input tensor, raw candidates, and filtered watched items.

### Administration & Diagnostics ([`app/api/v1/endpoints/admin.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/api/v1/endpoints/admin.py))
- `GET /api/v1/admin/system-health`: PostgreSQL, Redis, Celery worker ping, and model status.
- `GET /api/v1/admin/database-counts`: Real row counts across all SQL tables.
- `GET /api/v1/admin/model-info`: Reads active model sidecar JSON for hyperparameters and training metrics.
- `GET /api/v1/admin/latest-evaluation`: Reads stored empirical evaluation JSON with bootstrap CIs (or `NOT YET MEASURED`).
- `POST /api/v1/admin/trigger-retrain-model`: Asynchronously queues model retraining in Celery.
- `GET /api/v1/admin/training-status/latest`: Returns latest retraining job status (`idle`, `queued`, `running`, `successful`, `failed`).
- `GET /api/v1/admin/models/versions`: Lists archived versions in `models_store/versions/`.
- `POST /api/v1/admin/models/rollback`: Rolls back live model to an archived version with verification.

---

## 4. Frontend Component & Page Map

```
recommendation-frontend/src/
├── App.jsx                                  # Navigation routing, global layout wrapper
├── contexts/
│   ├── AuthContext.jsx                      # User session, JWT tokens, login/logout, global 401 interceptor
│   └── AppContext.jsx                       # Routing state, global toast notifications
├── pages/
│   ├── HomePage.jsx                         # Cinematic discovery: Hero billboard, personalized row, trending, catalogue
│   ├── MovieDetailPage.jsx                  # Backdrop hero, 1-5★ rating, watchlist button, reviews list, similar movies
│   ├── RecommendationsPage.jsx              # AI Picks grid, rank badges, explanation chips, progress banner
│   ├── OnboardingPage.jsx                   # Genre diversity picker for cold-start acceleration
│   ├── ProfilePage.jsx                      # User history, rating records, watchlist summary
│   ├── WatchlistPage.jsx                    # Dedicated saved movies grid with quick removal
│   └── (Admin Page)                         # Rendered via components/Admin/AdminPage.jsx
├── components/
│   ├── Admin/
│   │   └── AdminPage.jsx                    # System diagnostics, retrain polling, version rollback, evaluation charts
│   ├── Common/
│   │   ├── MovieCard.jsx                    # Poster card with 2:3 ratio, hover quick-actions, badges, rating stars
│   │   ├── PosterImage.jsx                  # Image loader with graceful editorial fallback on network failure
│   │   ├── RecommendationReason.jsx         # Embedding neighbor / genre overlap / popularity explanation chip
│   │   ├── SectionRow.jsx                   # Horizontal scrolling row with keyboard & arrow navigation
│   │   ├── RatingStars.jsx                  # Visual star rating display
│   │   ├── StarRatingInput.jsx              # Accessible 1-5★ interactive rating input
│   │   ├── WatchlistButton.jsx              # Toggle button with active saved state
│   │   ├── GenreBadge.jsx                   # Color-coded genre chip
│   │   └── RatingModal.jsx                  # Modal dialog for rating movies from cards
│   └── Reviews/
│       ├── ReviewForm.jsx                   # Accessible review editor with validation
│       └── ReviewCard.jsx                   # Author card with edit/delete controls for owner
└── services/
    └── ApiService.js                        # Unified HTTP client with automatic 401 session expiry handling
```

---

## 5. Machine Learning Pipeline File Map

- **Model Architecture:** [`app/services/recommender/model.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/services/recommender/model.py) (`SequentialRetrievalModel`)
- **Preprocessing & Windowing:** [`app/services/recommender/preprocessing.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/services/recommender/preprocessing.py) (`generate_examples_from_user_sequences`, `prepare_user_context_for_prediction`)
- **Training Pipeline:** [`app/services/recommender/train.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/services/recommender/train.py) (`train_model`, `verify_model_artifact`, `archive_and_version_model`, `rollback_model_version`)
- **Inference Pipeline:** [`app/services/recommender/predict.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/services/recommender/predict.py) (`get_recommendations_for_user`, `get_inference_trace_for_user`)
- **Explanations Engine:** [`app/services/recommender/explanation.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/services/recommender/explanation.py) (`generate_recommendation_reason`, `compute_cosine_similarity`)
- **Diversity & MMR Engine:** [`app/services/recommender/diversity.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/services/recommender/diversity.py) (`compute_dataset_diversity_summary`, `mmr_rerank`)
- **Leak-Free Evaluation:** [`app/services/recommender/evaluate.py`](file:///Users/vrinda/Desktop/full-stack-recommendation-system-main/app/services/recommender/evaluate.py) (`build_leave_last_out_splits`, `evaluate_model_leak_free`, `compute_bootstrap_ci`)
- **Storage Artifacts:**
  - Active Model: `models_store/gru4rec_model.keras`
  - Active Sidecar: `models_store/gru4rec_model.keras.json`
  - Version Archive: `models_store/versions/gru4rec_<timestamp>_<git_hash>.keras`
  - Evaluation Runs: `models_store/evaluation/experiments_summary.json` & `.csv`
