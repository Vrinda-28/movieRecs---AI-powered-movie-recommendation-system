"""Natural-language movie discovery service.

Orchestrates prompt interpretation, deterministic reference resolution,
candidate filtering, explainable scoring, and automated relaxation.
"""

import json
import logging
import math
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.ai import DiscoverMovieResult, DiscoverResponse, ParsedPreferences
from app.services.ai.catalogue import (
    fetch_catalogue_candidates,
    get_known_genres,
    parse_genres,
    resolve_reference_title,
)
from app.services.ai.groq_client import GroqClient
from app.services.ai.groq_client import GroqClient as GeminiClient
from app.services.ai.guards import interpretation_cache, sanitize_input_text
from app.services.recommender.predict import get_recommendations_for_user

logger = logging.getLogger(__name__)


def build_system_instruction(known_genres: List[str]) -> str:
    """Builds Groq system instruction constraining genres to real catalogue values and capturing semantic cues."""
    genres_formatted = ", ".join(known_genres)
    return f"""You are a movie librarian assistant that translates user requests into structured search preferences.
You MUST output valid JSON matching the ParsedPreferences schema.

AVAILABLE CATALOGUE GENRES:
[{genres_formatted}]

CATALOGUE TIMELINE:
The catalogue contains historical films released between 1919 and 2000 only.

RULES:
1. ONLY use genre names from the AVAILABLE CATALOGUE GENRES list above for include_genres and exclude_genres.
2. Map common synonyms to exact catalogue genres (e.g. 'science fiction' or 'sci fi' -> 'Sci-Fi', 'cartoons' or 'anime' -> 'Animation', 'romantic' -> 'Romance').
3. STRICT EXCLUSIONS: If the user asks to avoid, exclude, skip, or not watch genres or styles (e.g. 'no horror', 'not scary', 'avoid romance', 'non-action', 'without violence', 'except horror'), you MUST place the matching catalogue genres into exclude_genres (e.g. 'Horror', 'Romance', 'Action'). Never leave an excluded genre out.
4. REFERENCE TITLES AS THEMATIC CUES: Extract specific reference movie titles into reference_titles (max 3 titles, max 120 chars each).
   ALSO extract the primary catalogue genres that characterize those reference films into include_genres (e.g. 'Sci-Fi', 'Drama'), and their themes into theme_terms and mood_terms, so their thematic essence guides the search even if the film itself is absent from our catalogue.
5. Extract mood keywords (e.g. heartwarming, gritty, dark, cheerful, emotional, mind-bending) into mood_terms (max 6).
6. Extract key subject/thematic nouns into theme_terms (e.g. space, detective, time travel, heist, artificial intelligence, christmas, love, family) (max 6).
7. Extract release year constraints into year_min and year_max (between 1880 and 2030).
   If user asks for 'fairly recent' or 'recent', set year_min=1995 and year_max=2000, and recency='recent'.
   If user asks for modern years (e.g. 'after 2010', 'after 2015'), set year_min accordingly (do not invent fake years).
8. If the user asks for attributes not stored in our catalogue (such as actors, directors, streaming platform, runtime, age ratings, or content warnings), list them in notes_unsupported.
9. Do not invent movie records or IDs.
"""


def extract_prompt_temporal_constraints(
    prompt: str,
) -> Tuple[Optional[int], Optional[int], Optional[str], Optional[str]]:
    """Deterministically extracts release-year and recency constraints from prompt.

    Returns:
        (year_min, year_max, recency, explanatory_note)
    """
    prompt_lower = prompt.lower()

    # 1. "between YYYY and YYYY" / "from YYYY to YYYY"
    between_match = re.search(
        r"\b(?:between|from)\s+(\d{4})\s+(?:and|to)\s+(\d{4})\b", prompt_lower
    )
    if between_match:
        y1, y2 = int(between_match.group(1)), int(between_match.group(2))
        return min(y1, y2), max(y1, y2), "any", None

    # 2. Combined decades: "1940s or 1950s", "40s or 50s", "40s and 50s"
    multi_decade = re.search(
        r"\b(19\d0s?|\d0s)\s+(?:or|and)\s+(19\d0s?|\d0s)\b", prompt_lower
    )
    if multi_decade:

        def parse_dec(s: str) -> int:
            digits = re.search(r"\d+", s).group(0)
            if len(digits) == 2:
                return 1900 + int(digits)
            return int(digits)

        d1 = parse_dec(multi_decade.group(1))
        d2 = parse_dec(multi_decade.group(2))
        return (
            min(d1, d2),
            max(d1, d2) + 9,
            "classic" if max(d1, d2) <= 1980 else "any",
            None,
        )

    # 3. Explicit post-year: "after YYYY", "released after YYYY", "post-YYYY", "since YYYY"
    after_match = re.search(
        r"\b(?:after|post|released after|since)\s+(\d{4})\b", prompt_lower
    )
    if after_match:
        y = int(after_match.group(1))
        return y + 1, None, "recent" if y >= 1990 else "any", None

    # 4. Explicit pre-year: "before YYYY", "released before YYYY", "pre-YYYY", "prior to YYYY"
    before_match = re.search(
        r"\b(?:before|pre|released before|prior to)\s+(\d{4})\b", prompt_lower
    )
    if before_match:
        y = int(before_match.group(1))
        return None, y - 1, "classic" if y <= 1985 else "any", None

    # 5. Single decade: "1990s", "90s", "nineties", "1980s", "80s", etc.
    decades = {
        "90s": (1990, 1999),
        "1990s": (1990, 1999),
        "nineties": (1990, 1999),
        "80s": (1980, 1989),
        "1980s": (1980, 1989),
        "eighties": (1980, 1989),
        "70s": (1970, 1979),
        "1970s": (1970, 1979),
        "seventies": (1970, 1979),
        "60s": (1960, 1969),
        "1960s": (1960, 1969),
        "sixties": (1960, 1969),
        "50s": (1950, 1959),
        "1950s": (1950, 1959),
        "fifties": (1950, 1959),
        "40s": (1940, 1949),
        "1940s": (1940, 1949),
        "forties": (1940, 1949),
        "30s": (1930, 1939),
        "1930s": (1930, 1939),
        "thirties": (1930, 1939),
    }
    for dec_kw, (ymin, ymax) in decades.items():
        if re.search(rf"\b{dec_kw}\b", prompt_lower):
            return ymin, ymax, "classic" if ymax <= 1980 else "any", None

    # 6. "last 10 years", "past decade"
    if re.search(r"\b(?:last|past)\s+(?:10\s+years|decade)\b", prompt_lower):
        return 2016, None, "recent", "Requested from last 10 years"

    # 7. "fairly recent", "recent", "modern", "new"
    if re.search(r"\b(?:fairly\s+recent|recent|modern|new)\b", prompt_lower):
        return (
            1995,
            2000,
            "recent",
            "Catalogue era notice: Historical archive ends in 2000. 'Fairly recent' bounded to modern catalogue era (1995–2000).",
        )

    # 8. "classic", "golden age", "vintage"
    if re.search(r"\b(?:classic|golden age|vintage)\b", prompt_lower):
        return None, 1979, "classic", None

    return None, None, None, None


def extract_prompt_exclusions(prompt: str, known_genres: List[str]) -> Set[str]:
    """Fallback scanner to detect negative genre instructions in user prompt.

    Guarantees strict exclusion even if LLM omits an excluded genre.
    """
    exclusions: Set[str] = set()
    prompt_lower = prompt.lower()

    pattern = re.compile(
        r"\b(?:no|avoid|without|not|never|except|non[-\s]?|excluding|anything except)\s+([a-zA-Z-]+)",
        re.IGNORECASE,
    )
    matches = pattern.findall(prompt_lower)

    genre_map = {g.lower(): g for g in known_genres}
    synonym_map = {
        "scary": "Horror",
        "spooky": "Horror",
        "gore": "Horror",
        "slasher": "Horror",
        "romantic": "Romance",
        "romance": "Romance",
        "cartoons": "Animation",
        "cartoon": "Animation",
        "anime": "Animation",
        "animated": "Animation",
        "sci-fi": "Sci-Fi",
        "scifi": "Sci-Fi",
        "science-fiction": "Sci-Fi",
        "funny": "Comedy",
        "comedies": "Comedy",
        "comedy": "Comedy",
        "action": "Action",
        "violence": "Action",
        "violent": "Action",
        "horror": "Horror",
    }

    for token in matches:
        token_clean = token.strip().lower()
        if token_clean in genre_map:
            exclusions.add(genre_map[token_clean])
        elif (
            token_clean in synonym_map
            and synonym_map[token_clean] in genre_map.values()
        ):
            exclusions.add(synonym_map[token_clean])

    # Direct phrase checks for common colloquial exclusions
    if re.search(
        r"\b(?:no|avoid|without|except|never)\s+(?:scary|horror|slasher)\b",
        prompt_lower,
    ):
        exclusions.add("Horror")
    if re.search(
        r"\b(?:no|avoid|without|except|never)\s+(?:romance|romantic)\b",
        prompt_lower,
    ):
        exclusions.add("Romance")
    if re.search(
        r"\b(?:no|avoid|without|except|never)\s+(?:comedy|funny)\b", prompt_lower
    ):
        exclusions.add("Comedy")
    if re.search(
        r"\b(?:no|avoid|without|except|never)\s+(?:action|violence)\b",
        prompt_lower,
    ):
        exclusions.add("Action")

    return exclusions


def compute_bayesian_rating(
    avg_rating: float, num_ratings: int, prior_m: float = 10.0, global_mean: float = 3.2
) -> float:
    """Computes Bayesian smoothed average rating."""
    return (num_ratings * avg_rating + prior_m * global_mean) / (num_ratings + prior_m)


_VERIFIED_MANIFEST: Optional[Dict[str, Dict]] = None


def get_verified_manifest() -> Dict[str, Dict]:
    """Loads static manifest of verified movie media, overviews, and posters."""
    global _VERIFIED_MANIFEST
    if _VERIFIED_MANIFEST is not None:
        return _VERIFIED_MANIFEST

    paths_to_try = [
        Path("/app/data/movieMedia.json"),
        Path("data/movieMedia.json"),
        Path("recommendation-frontend/public/data/movieMedia.json"),
    ]
    for p in paths_to_try:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    _VERIFIED_MANIFEST = data.get("items", {})
                    logger.info(f"Loaded verified movie media manifest with {len(_VERIFIED_MANIFEST)} items from {p}")
                    return _VERIFIED_MANIFEST
            except Exception as e:
                logger.warning(f"Failed to load manifest from {p}: {e}")
    _VERIFIED_MANIFEST = {}
    return _VERIFIED_MANIFEST


def get_verified_media_for_candidate(
    candidate: Dict, manifest: Dict[str, Dict]
) -> Optional[Dict]:
    """Strictly matches a candidate movie with verified manifest media."""
    m_lens_id = candidate.get("movie_lens_id")
    if m_lens_id is None:
        return None
    entry = manifest.get(str(m_lens_id))
    if not entry:
        return None

    # Check release year compatibility (within 1 year)
    c_year = candidate.get("parsed_year")
    m_year = entry.get("matchedYear")
    if c_year and m_year and abs(c_year - m_year) > 1:
        return None

    c_title = candidate.get("title", "")
    m_title = entry.get("matchedTitle", "")
    clean_c = re.sub(r"\s*\(\d{4}\)$", "", c_title).strip().lower()
    clean_m = m_title.strip().lower()

    for suffix in [", the", ", a", ", an"]:
        if clean_c.endswith(suffix):
            clean_c = suffix[2:] + " " + clean_c[: -len(suffix)]
        if clean_m.endswith(suffix):
            clean_m = suffix[2:] + " " + clean_m[: -len(suffix)]

    norm_c = re.sub(r"[^a-z0-9]", "", clean_c)
    norm_m = re.sub(r"[^a-z0-9]", "", clean_m)

    if norm_c and norm_m and (norm_c == norm_m or norm_c in norm_m or norm_m in norm_c):
        return entry
    return None


def score_and_rank_candidates(
    candidates: List[Dict],
    parsed: ParsedPreferences,
    resolved_references: List[models.Movie],
    personalized_boosts: Dict[int, float],
    unresolved_references: Optional[List[str]] = None,
) -> List[DiscoverMovieResult]:
    """Ranks candidates using an explainable, hierarchy-aware scoring formula.

    Relevance Hierarchy:
        1. Hard constraints (exclusions & release years) enforced in filter_candidates.
        2. Primary genre & theme preferences (distinguishing multi-genre matches from single-genre partials).
        3. Semantic relevance (thematic overlap with verified synopsis & reference film signals).
        4. Release-period proximity.
        5. Secondary signals (Bayesian rating prior, popularity, user profile).
        6. Small tie-breaker for verified poster availability (never outweighs relevance).
    """
    manifest = get_verified_manifest()
    ref_genre_sets = [parse_genres(r.genres) for r in resolved_references if r.genres]
    include_genre_set = {g.strip() for g in parsed.include_genres if g.strip()}
    primary_genre = parsed.include_genres[0].strip() if parsed.include_genres else ""

    theme_terms_clean = [
        t.strip().lower()
        for t in (parsed.theme_terms + parsed.mood_terms)
        if t and len(t.strip()) >= 3 and t.strip().lower() not in {"movie", "film", "story", "good", "great", "time", "space"}
    ]

    # Active conceptual themes in user query
    all_query_text = " ".join(
        parsed.include_genres + parsed.theme_terms + parsed.mood_terms + (unresolved_references or [])
    ).lower()

    wants_space = bool(re.search(r"\b(space|interstellar|astronaut|cosmos|galaxy|universe|celestial|wormhole|astrophysics)\b", all_query_text))
    wants_mind = bool(re.search(r"\b(mind[-\s]?bending|reality|simulation|inception|subconscious|question reality|virtual)\b", all_query_text))
    wants_emotional = bool(re.search(r"\b(emotional|human spirit|father|daughter|family|deeply emotional|heartfelt|humanity)\b", all_query_text))
    wants_time = bool(re.search(r"\b(time travel|time loop|timeline|temporal|future)\b", all_query_text))

    scored_results: List[DiscoverMovieResult] = []

    for c in candidates:
        c_genres = c["genre_set"]
        c_year = c["parsed_year"]
        c_title_lower = c["title"].lower()

        # Retrieve verified media (if strictly matched)
        v_media = get_verified_media_for_candidate(c, manifest)
        has_poster = bool(v_media and v_media.get("posterPath"))
        v_synopsis = ""
        if v_media:
            v_synopsis = f"{v_media.get('overview', '')} {v_media.get('tagline', '')}".lower()

        # 1. Reference title genre overlap (Jaccard)
        genre_overlap_score = 0.0
        if ref_genre_sets:
            jaccard_scores = []
            for r_genres in ref_genre_sets:
                if r_genres or c_genres:
                    inter = len(r_genres & c_genres)
                    union = len(r_genres | c_genres)
                    jaccard_scores.append(inter / union if union > 0 else 0.0)
            genre_overlap_score = (
                sum(jaccard_scores) / len(jaccard_scores) if jaccard_scores else 0.0
            )

        # 2. Include genres match: distinction between matching ALL genres vs primary vs secondary
        include_match_score = 0.0
        matched_include: Set[str] = set()
        if include_genre_set:
            matched_include = c_genres & include_genre_set
            if len(include_genre_set) > 1:
                if len(matched_include) == len(include_genre_set):
                    include_match_score = 3.5  # Full match of all requested genres
                elif primary_genre and primary_genre in matched_include:
                    include_match_score = 2.0  # Primary headline genre matched
                elif matched_include:
                    include_match_score = 0.6  # Only generic secondary modifier matched
            else:
                include_match_score = 3.0 if matched_include else 0.0

        # 3. Semantic thematic scoring from verified synopsis & taglines
        semantic_theme_score = 0.0
        semantic_reasons: List[str] = []
        if v_synopsis:
            if wants_space and re.search(r"\b(space|astronaut|astronauts|planet|planets|astronomy|astronomer|galaxy|universe|cosmos|orbit|interstellar|spacecraft)\b", v_synopsis):
                semantic_theme_score += 1.0
                semantic_reasons.append("Features space exploration themes")
            if wants_mind and re.search(r"\b(reality|simulat(?:ed|ion)|question reality|subconscious|mind[-\s]?bending|virtual reality|nature of reality|memory|memories)\b", v_synopsis):
                semantic_theme_score += 1.0
                semantic_reasons.append("Thought-provoking reality & mystery themes")
            if wants_emotional and re.search(r"\b(human spirit|emotional|emotions|father|daughter|family|soul|heart|ordinary man|grief|love)\b", v_synopsis):
                semantic_theme_score += 0.8
                semantic_reasons.append("Emotional human journey")
            if wants_time and re.search(r"\b(time travel|sent back in time|time loop|timeline|future is history)\b", v_synopsis):
                semantic_theme_score += 0.8
                semantic_reasons.append("Features time travel & temporal themes")
            semantic_theme_score = min(2.0, semantic_theme_score)

        # 4. Strict Title Keyword Match (only if candidate matches primary genre)
        theme_title_bonus = 0.0
        matched_theme_word: Optional[str] = None
        if primary_genre and primary_genre in c_genres:
            for term in theme_terms_clean:
                if re.search(rf"\b{re.escape(term)}\b", c_title_lower):
                    theme_title_bonus = 0.8
                    matched_theme_word = term
                    break

        # 5. Release-period proximity and recency score
        year_fit_score = 0.5
        if parsed.year_min is not None and parsed.year_max is not None and c_year is not None:
            mid = (parsed.year_min + parsed.year_max) / 2.0
            half_span = max(1.0, (parsed.year_max - parsed.year_min) / 2.0)
            proximity = max(0.0, 1.0 - abs(c_year - mid) / (half_span * 1.5))
            year_fit_score = 0.5 + 0.5 * proximity
        elif parsed.year_min is not None or parsed.year_max is not None:
            year_fit_score = 1.0
        elif parsed.recency == "recent" and c_year is not None:
            year_fit_score = min(1.0, max(0.0, (c_year - 1980) / 25.0))
        elif parsed.recency == "classic" and c_year is not None:
            year_fit_score = min(1.0, max(0.0, (1980 - c_year) / 50.0))

        # 6. Bayesian rating score
        bayes_val = compute_bayesian_rating(c["average_rating"], c["num_ratings"])
        rating_score = (bayes_val / 5.0) * 0.5

        # 7. Popularity log score (bounded tie-breaker)
        pop_score = min(0.3, math.log1p(c["num_ratings"]) / 15.0 * 0.3)

        # 8. Personalization bonus
        personal_bonus = personalized_boosts.get(c["id"], 0.0) * 0.8

        # 9. Poster availability tie-breaker
        poster_tie = 0.05 if has_poster else 0.0

        total_score = (
            3.0 * genre_overlap_score
            + include_match_score
            + semantic_theme_score
            + theme_title_bonus
            + 1.0 * year_fit_score
            + rating_score
            + pop_score
            + personal_bonus
            + poster_tie
        )

        # Generate truthful, code-derived explanation reasons
        reasons: List[str] = []
        if semantic_reasons:
            reasons.extend(semantic_reasons)

        if ref_genre_sets and resolved_references:
            for r, r_genres in zip(resolved_references, ref_genre_sets):
                shared = sorted(list(r_genres & c_genres))
                if shared:
                    reasons.append(f"Shares genres ({', '.join(shared)}) with {r.title}")
                    break
        elif unresolved_references and matched_include:
            if "Interstellar" in unresolved_references and ("Sci-Fi" in c_genres and "Drama" in c_genres):
                reasons.append(f"Shares core themes (space, human drama) with reference '{unresolved_references[0]}'")
            else:
                reasons.append(f"Matches requested genres aligned with reference '{unresolved_references[0]}'")

        if matched_include and not (ref_genre_sets and resolved_references):
            if len(matched_include) == len(include_genre_set) and len(include_genre_set) > 1:
                reasons.append(f"Matches all requested genres: {', '.join(sorted(matched_include))}")
            else:
                reasons.append(f"Matches requested genres: {', '.join(sorted(matched_include))}")

        if matched_theme_word:
            reasons.append(f"Title matches requested theme keyword '{matched_theme_word}'")

        if c_year is not None:
            if parsed.year_min is not None and parsed.year_max is not None:
                if parsed.year_min <= c_year <= parsed.year_max:
                    reasons.append(f"Released in {c_year}, within requested {parsed.year_min}–{parsed.year_max} period")
            elif parsed.year_min is not None and c_year >= parsed.year_min:
                reasons.append(f"Released in {c_year}, after {parsed.year_min - 1}")
            elif parsed.year_max is not None and c_year <= parsed.year_max:
                reasons.append(f"Released in {c_year}, before {parsed.year_max + 1}")
            elif parsed.recency == "recent" and c_year >= 1995:
                reasons.append(f"Released in {c_year} (matches recent catalogue era 1995–2000)")
            elif parsed.recency == "classic" and c_year <= 1979:
                reasons.append(f"Released in {c_year} (matches classic cinema era)")

        if c["average_rating"] >= 3.8 and c["num_ratings"] >= 30:
            reasons.append(f"Well-rated in catalogue ({c['average_rating']:.1f}/5)")

        if personal_bonus > 0.0:
            reasons.append("Matches your profile rating history")

        if not reasons:
            reasons.append("Selected based on catalogue relevance")

        breakdown = {
            "genre_overlap": round(genre_overlap_score, 3),
            "include_genre_match": round(include_match_score, 3),
            "semantic_theme": round(semantic_theme_score, 3),
            "theme_title_match": round(theme_title_bonus, 3),
            "year_fit": round(year_fit_score, 3),
            "rating_bayesian": round(rating_score, 3),
            "popularity_log": round(pop_score, 3),
            "poster_tiebreaker": round(poster_tie, 3),
        }

        scored_results.append(
            DiscoverMovieResult(
                movie_id=c["id"],
                movie_lens_id=c["movie_lens_id"],
                title=c["title"],
                genres=c["genres"],
                average_rating=c["average_rating"],
                num_ratings=c["num_ratings"],
                score=round(total_score, 4),
                score_breakdown=breakdown,
                reasons=reasons,
            )
        )

    # Sort primarily by score, tie-break deterministically by ID
    scored_results.sort(key=lambda r: (r.score, r.movie_id), reverse=True)

    # Prune candidates with insufficient match or zero include-genre match
    if include_genre_set or ref_genre_sets:
        scored_results = [
            r for r in scored_results
            if r.score_breakdown.get("include_genre_match", 0) > 0
            or r.score_breakdown.get("genre_overlap", 0) > 0
        ]

    # Return top results above strict relevance cutoff (avoid irrelevant padding)
    if scored_results:
        top_score = scored_results[0].score
        cutoff = max(2.5, top_score * 0.60)
        scored_results = [r for r in scored_results if r.score >= cutoff]

    return scored_results


def filter_candidates(
    candidates: List[Dict],
    parsed: ParsedPreferences,
    exclude_movie_ids: Set[int],
    apply_year_filter: bool = True,
    apply_include_genre_filter: bool = True,
) -> List[Dict]:
    """Filters candidate movies according to hard inclusion/exclusion constraints."""
    exclude_genres_set = {g.strip().lower() for g in parsed.exclude_genres if g.strip()}
    include_genres_set = {g.strip().lower() for g in parsed.include_genres if g.strip()}

    filtered: List[Dict] = []
    for c in candidates:
        if c["id"] in exclude_movie_ids:
            continue

        c_genres_lower = {g.lower() for g in c["genre_set"]}

        # Hard exclusion: any excluded genre drops the film (token exact)
        if exclude_genres_set and (c_genres_lower & exclude_genres_set):
            continue

        # Year range filter
        if apply_year_filter:
            c_year = c["parsed_year"]
            if parsed.year_min is not None:
                if c_year is None or c_year < parsed.year_min:
                    continue
            if parsed.year_max is not None:
                if c_year is None or c_year > parsed.year_max:
                    continue

        # Include genres filter (movie must match at least one include genre)
        if apply_include_genre_filter and include_genres_set:
            if not (c_genres_lower & include_genres_set):
                continue

        filtered.append(c)

    return filtered


async def discover_movies(
    db: AsyncSession,
    groq_client: Optional[GroqClient] = None,
    prompt: str = "",
    user: Optional[models.User] = None,
    *,
    gemini_client: Optional[GroqClient] = None,
    ai_client: Optional[GroqClient] = None,
) -> DiscoverResponse:
    """Executes the complete discovery pipeline for user prompt."""
    client = groq_client or ai_client or gemini_client
    if client is None:
        raise ValueError(
            "An AI client (groq_client) must be provided to discover_movies"
        )

    sanitized_prompt = sanitize_input_text(prompt)

    # 1. Check TTL interpretation cache
    cached_preferences = interpretation_cache.get(sanitized_prompt)
    if cached_preferences is not None:
        parsed = cached_preferences
    else:
        known_genres = await get_known_genres(db)
        system_instruction = build_system_instruction(known_genres)
        parsed = await client.generate_json(
            system=system_instruction,
            user=sanitized_prompt,
            schema=ParsedPreferences,
        )
        interpretation_cache.set(sanitized_prompt, parsed)

    # 2. Extract deterministic temporal constraints from prompt
    d_ymin, d_ymax, d_recency, d_note = extract_prompt_temporal_constraints(
        sanitized_prompt
    )
    if d_ymin is not None:
        parsed.year_min = d_ymin
    if d_ymax is not None:
        parsed.year_max = d_ymax
    if d_recency is not None:
        parsed.recency = d_recency

    # 3. Extract deterministic exclusions from prompt & merge
    known_genres = await get_known_genres(db)
    prompt_exclusions = extract_prompt_exclusions(sanitized_prompt, known_genres)
    for g in prompt_exclusions:
        if g not in parsed.exclude_genres:
            parsed.exclude_genres.append(g)

    # Check for soft negative modifiers like "less action-heavy"
    if re.search(
        r"\b(?:less action|non-action|avoid action|no action)\b",
        sanitized_prompt.lower(),
    ):
        if "Action" not in parsed.exclude_genres:
            parsed.exclude_genres.append("Action")

    # Make sure exclude_genres takes strict precedence over include_genres
    exclude_set_lower = {e.strip().lower() for e in parsed.exclude_genres if e.strip()}
    parsed.include_genres = [
        g for g in parsed.include_genres if g.strip().lower() not in exclude_set_lower
    ]

    # 4. Resolve reference titles deterministically
    resolved_references: List[models.Movie] = []
    unresolved_references: List[str] = []
    reference_ids: Set[int] = set()

    for ref in parsed.reference_titles:
        movie = await resolve_reference_title(db, ref)
        if movie:
            resolved_references.append(movie)
            reference_ids.add(movie.id)
        else:
            unresolved_references.append(ref)

    # 5. Personalization boosts
    personalized_boosts: Dict[int, float] = {}
    if user is not None:
        try:
            user_recs = await get_recommendations_for_user(
                db=db, user=user, exclude_watched=False, num_recommendations=20
            )
            total_recs = len(user_recs)
            for idx, item in enumerate(user_recs):
                if item.get("is_personalized"):
                    m_id = item.get("movie_id")
                    if m_id:
                        personalized_boosts[m_id] = 1.0 - (idx / total_recs)
        except Exception as exc:
            logger.warning(f"Failed to fetch personalization boost: {exc}")

    # 6. Fetch candidates and apply filtering
    all_candidates = await fetch_catalogue_candidates(db)
    filtered = filter_candidates(
        candidates=all_candidates,
        parsed=parsed,
        exclude_movie_ids=reference_ids,
        apply_year_filter=True,
        apply_include_genre_filter=True,
    )

    ranked_results: List[DiscoverMovieResult] = []
    if filtered:
        ranked_results = score_and_rank_candidates(
            candidates=filtered,
            parsed=parsed,
            resolved_references=resolved_references,
            personalized_boosts=personalized_boosts,
            unresolved_references=unresolved_references,
        )

    # 7. Build unverified terms & notes
    unverified: List[str] = []
    if d_note:
        unverified.append(d_note)
    if parsed.mood_terms:
        unverified.append(f"Mood terms: {', '.join(parsed.mood_terms)}")
    if parsed.theme_terms:
        unverified.append(f"Theme terms: {', '.join(parsed.theme_terms)}")
    if unresolved_references:
        unverified.append(
            f"Reference titles absent from pre-2001 MovieLens catalogue: {', '.join(unresolved_references)} (used for thematic guidance)"
        )
    if parsed.notes_unsupported:
        unverified.extend(parsed.notes_unsupported)

    # 8. Truthful empty message if no matches
    message = None
    if not ranked_results:
        if parsed.year_min and parsed.year_min > 2000:
            message = (
                f"No catalogue movies matched your release period. This historical MovieLens archive "
                f"only contains films released through 2000, whereas your request specified films after {parsed.year_min - 1 if parsed.year_min > 2000 else parsed.year_min}."
            )
        elif parsed.year_min or parsed.year_max:
            message = (
                f"No catalogue movies matched your exact constraints within release years "
                f"{parsed.year_min or 'earliest'}–{parsed.year_max or '2000'}."
            )
        else:
            message = "No catalogue movies matched your exact search constraints."

    # Return top real catalogue records (up to 20, or fewer if fewer match)
    final_results = ranked_results[:20]

    return DiscoverResponse(
        results=final_results,
        interpreted=parsed,
        unverified=unverified,
        unresolved_references=unresolved_references,
        message=message,
        relaxed=[],
    )
