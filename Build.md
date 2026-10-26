# Build.md — Groq AI Integration for MovieRecs

Two features only: **(A) natural-language movie discovery** and **(B) "Ask About Movies"**.
Backend-heavy, small additive changes. GRU4Rec, the existing UI, auth, ratings and Docker stay as they are.
Migrated from Gemini to Groq (`groq==1.7.0` using official `AsyncGroq` client).

Put this file in the repository root. Run **Prompt 1 → Prompt 2 → Prompt 3 in order**, one at a time, and review after each.

---

## SECTION A — GLOBAL RULES (apply to every prompt)

1. **Scope.** Add exactly two features. Do not redesign the frontend, rewrite anything, replace GRU4Rec, touch `models_store/`, `app/services/recommender/*`, training, Celery tasks, Redis/Postgres/Compose service definitions, or the DB schema. **No Alembic migration, no new tables.** No live TMDB integration. No chatbot landing page.
2. **Inspect first, never assume.** Verify each path, route, field and component named below against the real repo before use. If the real repo differs, follow the real repo and say so in your report.
3. **Secrets.** `GROQ_API_KEY` is read only in the backend from the environment. Never in Vite variables, frontend code, API responses, logs, exceptions, test fixtures or the committed `.env.example` (placeholders only). The status endpoint returns only a boolean and the model name.
4. **Grounding.** The database is the only source of movie records. The model may *choose, rank and phrase*; it may never *create* a movie ID, title, poster, rating or catalogue entry. Every ID in any response is re-checked against the DB on the backend before it leaves.
5. **Untrusted input.** User prompts, chat history and model output are all untrusted. Model output is parsed with Pydantic, clamped and whitelisted before it touches code paths or SQL. Never build SQL strings from model output. Never render model text as HTML.
6. **Honesty.** If the catalogue does not hold an attribute (mood, themes, plot, cast, content warnings, age rating, runtime, streaming availability), the system says it cannot be verified. It must never present guesses as verified, and popularity is never evidence of mood or theme match.
7. **No fake AI.** No hard-coded responses, no mock output in production code paths. Mocks exist only inside tests.
8. **Never claim a test passed unless you ran it and saw the result.** Never claim recommendation accuracy improved; no accuracy evaluation is part of this task.
9. **Backward compatibility.** Existing endpoints and response shapes do not change. The app works with `GROQ_API_KEY` unset (AI features show a clear "AI is not configured" state; everything else behaves as before).
10. **Fits the repo style:** async FastAPI + SQLAlchemy, `settings` object in `app/core/config.py`, `deps.get_db` / `deps.get_current_active_user`, Pydantic v2 schemas, pytest + pytest-asyncio with the in-memory SQLite `client` and `db_session` fixtures from `tests/conftest.py`, `black` + `isort` formatting (`make lint` runs `black --check .`), frontend uses the `ApiService` object (fetch-based), state-based navigation via `AppContext` (no router), Tailwind classes already in use. Run `black` and `isort` on every Python file you add or edit.

---

## SECTION B — REPOSITORY FACTS (from the snapshot; VERIFY each)

| Area | Snapshot fact | Why it matters |
|---|---|---|
| Movie table (`app/db/models.py`) | columns: `id`, `title`, `genres` (string), `resource_url`, `movie_lens_id`, timestamps. **No overview, cast, runtime, poster, backdrop, year, age rating, content warnings.** | This is all the grounding data the backend has. Verify whether your local repo added more (reviews, watchlist, media fields). |
| Title/year | The year lives **inside the title** (`"Toy Story (1995)"`), and genres are **pipe-delimited** (`"Animation|Children's|Comedy"`). | Parse year with a regex in Python. Genres are matched by splitting on `|`, **not** with `LIKE %x%` (that would make "Sci-Fi" match unrelated strings and "Action" match "Action-Adventure"). |
| `resource_url` | The seed script fills it with **placeholder YouTube URLs unrelated to the film**. | **Never** send it to Gemini or treat it as data. |
| Ratings | `average_rating` / `num_ratings` computed in `crud.movie.get_multi_with_rating_summary`, `get`, `get_most_popular` (`app/db/crud.py`). | Quality/popularity signal only. |
| Recommender | `app/services/recommender/predict.py::get_recommendations_for_user(db, user, exclude_watched, num_recommendations)` returns dicts with `movie_id, movie_lens_id, title, resource_url, genres, is_personalized`. Cold-start → popularity fallback (`is_personalized: False`). | Reuse as an optional personalisation signal; **do not modify it**. |
| Routes | `app/api/v1/api.py` mounts users, movies, ratings, recommendations, admin under `/api/v1`. | Add one new router `ai`, same pattern. |
| Auth deps | `deps.get_current_active_user`, `deps.get_db` in `app/api/deps.py`. | Require login for AI endpoints (cost control). |
| Config | `app/core/config.py` `Settings` class reads `os.getenv`; `.env` is loaded by `python-dotenv` and by Compose `env_file`. | Add `GEMINI_*` settings here. |
| Docker | `Dockerfile` uses `python:3.10-slim`, installs `requirements.txt`, copies `./app`. Compose mounts `./app` and has `.env` in `env_file`. | A new pip dependency needs `docker compose up --build`. New code under `app/` is picked up by `--reload`. |
| Frontend | `recommendation-frontend/`: React 19, Vite 6, Tailwind v4, `src/services/ApiService.js`, `src/contexts/{AppContext,AuthContext}.jsx`, `src/components/Common/MovieCard.jsx`, pages `HomePage`, `RecommendationsPage`, `MovieDetailPage`. Navigation is `navigateTo("movieDetail", id)`. No test runner configured. | Reuse `MovieCard` and `ApiService`; add no packages. |
| Tests | `tests/test_{unit,integration,system}.py`, 22 tests, in-memory SQLite. | Record a green baseline before changing anything. |
| Env files | `.env`, `app/.env`, `recommendation-frontend/.env` exist in the zip; `.gitignore` ignores `.env` and `*.env`. | Confirm none of them is tracked by git (`git ls-files | grep -i env`). Do not copy values anywhere. |

---

## SECTION C — DESIGN DECISIONS (already made; implement as written)

**C1. SDK and model.** Use the official **`google-genai`** SDK (`pip install google-genai`; the old `google-generativeai` is deprecated). Default model `gemini-3.8-flash` via `GEMINI_MODEL`. Pin the version in `requirements.txt`.

**C2. Where the code lives.**
```
app/services/ai/__init__.py
app/services/ai/gemini_client.py   # the only module that imports google.genai
app/services/ai/catalogue.py       # DB-backed catalogue helpers (parse year/genres, candidate retrieval, similarity)
app/services/ai/discovery.py       # prompt -> prefs -> retrieve -> rank
app/services/ai/ask.py             # grounded Q&A
app/services/ai/guards.py          # sanitising, size limits, rate limit, cache
app/schemas/ai.py
app/api/v1/endpoints/ai.py
tests/test_ai_*.py
```

**C3. Endpoints.**
- `GET  /api/v1/ai/status` → `{ "enabled": bool, "model": "<name>" }`. No key, no secrets.
- `POST /api/v1/ai/discover` body `{ "prompt": str (3..500 chars) }`
- `POST /api/v1/ai/ask` body `{ "question": str (3..500), "movie_id": int | null, "history": [ {role:"user"|"assistant", text:str(<=500)} ] (<=6 items) }`

---

## COMPLETION LOG

| Prompt | Status | Evidence & Test Summary | Notes |
|---|---|---|---|
| **Prompt 1: Gemini backend foundation** | **DONE** | 15/15 AI unit tests passed (`tests/test_ai_*.py`); 59/59 full test suite passed (`tests/`). `black --check` and `isort --check-only` passed. Zero secret leaks. | SDK pinned: `google-genai==2.31.0`. Default model `gemini-3.8-flash`. All error types mapped to safe status codes (502, 429, 503, 504). |
| **Prompt 2: Frontend integration** | **DONE** | `npm run lint` passed (0 errors, 2 pre-existing fast-refresh warnings). `npm run build` completed in 649ms without errors. Zero key strings in `dist/`. | Embedded `AiPromptPanel` in `HomePage.jsx` and `AskMoviePanel` in `MovieDetailPage.jsx`. Plain text rendering, AbortControllers, retryable errors. |
| **Prompt 3: Integration, testing, and documentation** | **DONE** | `pytest tests/ -vv --cov=app`: 59 passed in 19.68s, 58% overall app coverage. `docker compose config -q`: valid. README & `.env.example` updated. | Full regression passed without regressions. Key never leaked in logs, responses, or client bundle. |
| **Migration: Gemini to Groq Transition** | **DONE** | 16/16 AI tests passed (`tests/test_ai_*.py`); 60/60 full test suite passed (`tests/`). `requirements.txt` replaced `google-genai` with `groq==1.7.0`. | `GroqClient` with `groq.AsyncGroq`, `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_TIMEOUT_SECONDS`, JSON schema injection, robust error mapping, and secret key redaction (`gsk_...` & `AIza...`). |

---

## FINAL ACCEPTANCE CHECKLIST

- [x] Both features work against real catalogue data; no invented movies anywhere
- [x] Groq key only in backend env; absent from frontend bundle, responses, logs, repo
- [x] Excluded genres and year ranges respected; token-exact genre matching
- [x] Malformed / hallucinated model output handled; ids re-validated against DB
- [x] Ask answers distinguish catalogue facts, interpretation and "cannot verify"
- [x] Groq failures (auth, quota, timeout, network, bad output, model not found) don't crash the app
- [x] App fully functional with the key unset (returns 503 `ai_not_configured`, UI shows friendly note)
- [x] GRU4Rec, recommendation endpoints, auth, ratings, UI structure unchanged
- [x] Existing tests pass (44/44 baseline + 16/16 AI tests = 60/60 passing); lint + build pass
- [x] Docker compose valid (`docker compose config -q` passed)
- [x] README and `.env.example` updated with Groq variables
