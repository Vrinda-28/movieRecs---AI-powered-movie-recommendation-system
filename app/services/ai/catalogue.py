"""Catalogue helpers for AI discovery and grounded Q&A.

Extracts years and genres, resolves reference titles deterministically,
fetches candidates with rating aggregates, and builds similarity sets.
Works consistently across SQLite (tests) and PostgreSQL.
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import Float as SQLFloat
from sqlalchemy import cast, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models import Movie, Rating

# Standard MovieLens 1M genre taxonomy
DEFAULT_MOVIELENS_GENRES = [
    "Action",
    "Adventure",
    "Animation",
    "Children's",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Fantasy",
    "Film-Noir",
    "Horror",
    "Musical",
    "Mystery",
    "Romance",
    "Sci-Fi",
    "Thriller",
    "War",
    "Western",
]

_known_genres_cache: Optional[List[str]] = None


def parse_year_from_title(title: str) -> Optional[int]:
    """Extracts 4-digit release year from movie title.

    Examples:
        "Toy Story (1995)" -> 1995
        "American President, The (1995)" -> 1995
        "Metropolis" -> None
    """
    if not title:
        return None
    match = re.search(r"\((\d{4})\)\s*$", title.strip())
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def parse_genres(genres_str: Optional[str]) -> Set[str]:
    """Parses pipe-separated genre string into a set of trimmed genre tokens.

    Example:
        "Animation|Children's|Comedy" -> {"Animation", "Children's", "Comedy"}
    """
    if not genres_str:
        return set()
    return {g.strip() for g in genres_str.split("|") if g.strip()}


def strip_year_from_title(title: str) -> str:
    """Removes trailing year in parentheses from title."""
    return re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()


def normalize_title_for_comparison(title: str) -> str:
    """Normalizes title for case-insensitive, punctuation-stripped matching.

    Handles inverted English articles (", The", ", A", ", An").
    """
    clean = strip_year_from_title(title).strip()

    # Invert trailing articles: "Matrix, The" -> "The Matrix"
    for article in (", The", ", the", ", A", ", a", ", An", ", an"):
        if clean.endswith(article):
            prefix = article.replace(", ", "").strip().title()
            clean = f"{prefix} {clean[:-len(article)]}".strip()
            break

    # Strip punctuation and collapse whitespace
    clean = re.sub(r"[^\w\s]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip().lower()
    return clean


async def get_known_genres(db: AsyncSession) -> List[str]:
    """Retrieves all distinct genres present in the database.

    Falls back to the standard MovieLens genre taxonomy if none are found.
    """
    global _known_genres_cache
    if _known_genres_cache:
        return _known_genres_cache

    stmt = select(Movie.genres).distinct()
    result = await db.execute(stmt)
    raw_genres_list = result.scalars().all()

    all_genres: Set[str] = set()
    for row in raw_genres_list:
        if row:
            for g in row.split("|"):
                cleaned = g.strip()
                if cleaned:
                    all_genres.add(cleaned)

    if not all_genres:
        _known_genres_cache = sorted(DEFAULT_MOVIELENS_GENRES)
    else:
        _known_genres_cache = sorted(list(all_genres))

    return _known_genres_cache


async def resolve_reference_title(
    db: AsyncSession, reference_title: str
) -> Optional[Movie]:
    """Deterministically resolves a user-supplied reference title against the catalogue.

    Returns the matching Movie ORM instance, or None if unresolved.
    Never invents or guesses a title.
    """
    if not reference_title or not reference_title.strip():
        return None

    target_norm = normalize_title_for_comparison(reference_title)
    if not target_norm:
        return None

    # Load catalogue movie titles and IDs
    stmt = select(Movie)
    result = await db.execute(stmt)
    movies = result.scalars().all()

    # 1. Exact match on normalized title (ignoring year and inverted articles)
    for m in movies:
        if normalize_title_for_comparison(m.title) == target_norm:
            return m

    # 2. Check if reference title is an exact substring match when length is substantial
    if len(target_norm) >= 5:
        candidates = [
            m for m in movies if target_norm == normalize_title_for_comparison(m.title)
        ]
        if candidates:
            return candidates[0]

    return None


async def fetch_catalogue_candidates(db: AsyncSession) -> List[Dict]:
    """Fetches all movies from the catalogue joined with average ratings and counts.

    Returns a list of dicts:
    {
        "id": int,
        "movie_lens_id": int | None,
        "title": str,
        "genres": str | None,
        "parsed_year": int | None,
        "genre_set": Set[str],
        "average_rating": float,
        "num_ratings": int,
    }
    """
    rating_summary = (
        select(
            Rating.movie_id,
            func.coalesce(cast(func.avg(Rating.rating), SQLFloat), 0.0).label(
                "average_rating"
            ),
            func.count(Rating.id).label("num_ratings"),
        )
        .group_by(Rating.movie_id)
        .subquery("rs")
    )

    stmt = select(
        Movie.id,
        Movie.movie_lens_id,
        Movie.title,
        Movie.genres,
        func.coalesce(rating_summary.c.average_rating, 0.0).label("average_rating"),
        func.coalesce(rating_summary.c.num_ratings, 0).label("num_ratings"),
    ).outerjoin(rating_summary, Movie.id == rating_summary.c.movie_id)

    result = await db.execute(stmt)
    candidates = []
    for row in result.all():
        m_id, m_lens_id, title, genres, avg_r, num_r = row
        candidates.append(
            {
                "id": m_id,
                "movie_lens_id": m_lens_id,
                "title": title,
                "genres": genres,
                "parsed_year": parse_year_from_title(title),
                "genre_set": parse_genres(genres),
                "average_rating": float(avg_r) if avg_r is not None else 0.0,
                "num_ratings": int(num_r) if num_r is not None else 0,
            }
        )
    return candidates


async def find_similar_catalogue_movies(
    db: AsyncSession, target_movie_id: int, limit: int = 12
) -> List[Dict]:
    """Finds up to `limit` deterministic similar catalogue movies for a given movie.

    Ranking formula:
        genre_jaccard = |A ∩ B| / |A ∪ B|
        year_proximity = 1 / (1 + |year_A - year_B| / 10)
        quality_score = (avg_rating / 5.0)
        similarity = 3.0 * genre_jaccard + 1.0 * year_proximity + 0.5 * quality_score
    """
    candidates = await fetch_catalogue_candidates(db)
    target = next((c for c in candidates if c["id"] == target_movie_id), None)
    if not target:
        return []

    target_genres = target["genre_set"]
    target_year = target["parsed_year"]

    scored_candidates = []
    for c in candidates:
        if c["id"] == target_movie_id:
            continue

        c_genres = c["genre_set"]
        if target_genres and c_genres:
            intersection = len(target_genres & c_genres)
            union = len(target_genres | c_genres)
            jaccard = intersection / union if union > 0 else 0.0
        else:
            jaccard = 0.0

        c_year = c["parsed_year"]
        if target_year is not None and c_year is not None:
            year_prox = 1.0 / (1.0 + abs(target_year - c_year) / 10.0)
        else:
            year_prox = 0.5

        quality = (c["average_rating"] / 5.0) if c["average_rating"] else 0.5
        sim_score = 3.0 * jaccard + 1.0 * year_prox + 0.5 * quality

        scored_candidates.append({**c, "similarity_score": sim_score})

    scored_candidates.sort(key=lambda x: (x["similarity_score"], x["id"]), reverse=True)
    return scored_candidates[:limit]


async def get_compact_user_profile(db: AsyncSession, user_id: int) -> Dict[str, object]:
    """Extracts an anonymised summary profile of user's rating preferences.

    Contains rating count and top preferred genres (from ratings >= 4.0).
    NEVER contains user email or user ID.
    """
    stmt = (
        select(Rating.rating, Movie.genres)
        .join(Movie, Rating.movie_id == Movie.id)
        .filter(Rating.user_id == user_id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    total_ratings = len(rows)
    genre_high_counts: Dict[str, int] = {}

    for rating_val, genres_str in rows:
        if rating_val >= 4.0 and genres_str:
            for g in genres_str.split("|"):
                cleaned = g.strip()
                if cleaned:
                    genre_high_counts[cleaned] = genre_high_counts.get(cleaned, 0) + 1

    top_genres = sorted(
        genre_high_counts.keys(), key=lambda g: genre_high_counts[g], reverse=True
    )[:4]

    return {
        "rating_count": total_ratings,
        "top_genres": top_genres,
    }
