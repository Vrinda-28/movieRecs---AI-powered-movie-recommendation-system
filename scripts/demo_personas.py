#!/usr/bin/env python3
"""
scripts/demo_personas.py — Personalization Demonstration Script (Viva-Critical)

Creates two throwaway demo personas with distinct genre preferences:
  - Persona A: Action / Sci-Fi Enthusiast (e.g., Matrix, Star Wars, Terminator)
  - Persona B: Romance / Drama Lover (e.g., Titanic, Casablanca, Before Sunrise)

Rates movies in ascending chronological order, calls the REAL recommendation function
`get_recommendations_for_user`, and prints both lists side-by-side with genre distribution
and exact list overlap percentage.

Truthful reporting:
  If both personas receive overlapping results, it documents whether the difference
  is driven by GRU4Rec sequential representations or popularity backfill, and notes
  the impact of training data distribution.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure app is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.db import crud, models
from app.db.session import AsyncSessionLocal
from app.schemas.rating import RatingCreate
from app.schemas.user import UserCreate
from app.services.recommender.predict import (
    get_inference_trace_for_user,
    get_recommendations_for_user,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def genre_distribution(recs: List[Dict]) -> Dict[str, int]:
    dist: Dict[str, int] = {}
    for r in recs:
        genres = (r.get("genres") or "").split("|")
        for g in genres:
            g = g.strip()
            if g:
                dist[g] = dist.get(g, 0) + 1
    return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))


async def find_movies_by_genre(
    db, primary_genre: str, count: int = 5
) -> List[models.Movie]:
    """Finds popular movies containing the given genre string."""
    movies = await crud.movie.get_multi(db, limit=200)
    matched = [
        m for m in movies
        if m.genres and primary_genre.lower() in m.genres.lower()
    ]
    return matched[:count]


async def run_persona_demo():
    print("=" * 78)
    print("  PERSONALIZATION DEMO: DIVERGENT PERSONA RECOMMENDATION AUDIT")
    print("=" * 78)
    print(f"Model Path: {settings.MODEL_PATH}")
    print(f"Context Window (MAX_CONTEXT_LENGTH): {settings.MAX_CONTEXT_LENGTH}")
    print(f"Cold Start Threshold (MIN_SEQUENCE_LENGTH): {settings.MIN_SEQUENCE_LENGTH}\n")

    async with AsyncSessionLocal() as db:
        # Step 1: Ensure demo users exist
        user_a_email = f"persona_action_{int(time.time())}@demo.local"
        user_b_email = f"persona_romance_{int(time.time())}@demo.local"

        user_a = await crud.user.create(
            db, obj_in=UserCreate(email=user_a_email, password="demopassword123")
        )
        user_b = await crud.user.create(
            db, obj_in=UserCreate(email=user_b_email, password="demopassword123")
        )

        # Step 2: Select distinct movies for each persona
        action_movies = await find_movies_by_genre(db, "Action", count=5)
        if len(action_movies) < 3:
            # Fallback to Sci-Fi or any available
            action_movies = await find_movies_by_genre(db, "Sci-Fi", count=5)

        romance_movies = await find_movies_by_genre(db, "Romance", count=5)
        if len(romance_movies) < 3:
            romance_movies = await find_movies_by_genre(db, "Drama", count=5)

        print(f"[Persona A] Action/Sci-Fi Fan: {user_a.email}")
        base_time = int(time.time()) - 10000
        for idx, m in enumerate(action_movies):
            t = base_time + (idx * 60)
            await crud.rating.create_with_owner(
                db,
                obj_in=RatingCreate(movie_id=m.id, rating=5.0, timestamp=t),
                user_id=user_a.id,
            )
            print(f"  ({idx+1}) Rated 5.0★: [{m.id}] {m.title} ({m.genres}) at t={t}")

        print(f"\n[Persona B] Romance/Drama Fan: {user_b.email}")
        for idx, m in enumerate(romance_movies):
            t = base_time + (idx * 60)
            await crud.rating.create_with_owner(
                db,
                obj_in=RatingCreate(movie_id=m.id, rating=5.0, timestamp=t),
                user_id=user_b.id,
            )
            print(f"  ({idx+1}) Rated 5.0★: [{m.id}] {m.title} ({m.genres}) at t={t}")

        # Step 3: Run real inference for both personas
        count = 10
        recs_a = await get_recommendations_for_user(
            db, user=user_a, exclude_watched=True, num_recommendations=count
        )
        recs_b = await get_recommendations_for_user(
            db, user=user_b, exclude_watched=True, num_recommendations=count
        )

        # Step 4: Display recommendations side-by-side
        print("\n" + "=" * 78)
        print("  RECOMMENDATION RESULTS COMPARISON")
        print("=" * 78)

        print(f"\n{'Rank':<5} | {'Persona A (Action/Sci-Fi)':<34} | {'Persona B (Romance/Drama)':<34}")
        print("-" * 78)

        max_len = max(len(recs_a), len(recs_b))
        for i in range(max_len):
            item_a = recs_a[i] if i < len(recs_a) else {}
            item_b = recs_b[i] if i < len(recs_b) else {}

            title_a = (item_a.get("title") or "N/A")[:30]
            src_a = item_a.get("source", "?")[:3]
            str_a = f"{title_a} [{src_a}]"

            title_b = (item_b.get("title") or "N/A")[:30]
            src_b = item_b.get("source", "?")[:3]
            str_b = f"{title_b} [{src_b}]"

            print(f"{i+1:<5} | {str_a:<34} | {str_b:<34}")

        # Step 5: Metrics & Overlap Analysis
        ids_a = {r["movie_id"] for r in recs_a if "movie_id" in r}
        ids_b = {r["movie_id"] for r in recs_b if "movie_id" in r}
        common = ids_a & ids_b
        overlap_pct = (len(common) / count) * 100 if count else 0.0

        print("\n" + "-" * 78)
        print(f"Total Shared Recommendations: {len(common)} / {count} ({overlap_pct:.1f}% list overlap)")
        if common:
            print(f"Shared Movie IDs: {sorted(list(common))}")

        print("\nGenre Distribution in Recommendations:")
        print(f"  Persona A Recs Genres: {genre_distribution(recs_a)}")
        print(f"  Persona B Recs Genres: {genre_distribution(recs_b)}")

        # Step 6: Inference audit trace summary
        trace_a = await get_inference_trace_for_user(db, user=user_a, num_recommendations=count)
        trace_b = await get_inference_trace_for_user(db, user=user_b, num_recommendations=count)

        print("\nAudit Trace Summary:")
        print(f"  Persona A Padded Input: {trace_a.get('padded_input_window')}")
        print(f"  Persona A Raw Model Ids: {trace_a.get('raw_retrieved_ids')[:5]}...")
        print(f"  Persona B Padded Input: {trace_b.get('padded_input_window')}")
        print(f"  Persona B Raw Model Ids: {trace_b.get('raw_retrieved_ids')[:5]}...")

        # Truthful summary
        print("\n" + "=" * 78)
        print("  EVALUATION CONCLUSION")
        print("=" * 78)
        if trace_a.get("model_available"):
            print("✓ GRU4Rec sequential model was evaluated live on real user input sequences.")
            print(f"✓ Persona A received {sum(1 for r in recs_a if r.get('source') == 'gru4rec')} model-generated picks.")
            print(f"✓ Persona B received {sum(1 for r in recs_b if r.get('source') == 'gru4rec')} model-generated picks.")
        else:
            print("ℹ Model checkpoint unavailable; system safely reverted to popularity fallback.")
        print("=" * 78)


if __name__ == "__main__":
    asyncio.run(run_persona_demo())
