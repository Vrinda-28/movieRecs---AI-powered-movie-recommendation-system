import argparse
import asyncio
import logging
import os
import random
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import requests
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.db import crud
from app.db.models import Movie, Rating, User
from app.db.session import AsyncSessionLocal, Base, async_engine
from app.schemas.movie import MovieCreate
from app.schemas.rating import RatingCreate
from app.schemas.user import UserCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOVIELENS_1M_URL = "https://files.grouplens.org/datasets/movielens/ml-1m.zip"
DATA_BASE_PATH = Path("/app/data") if Path("/app/data").exists() else Path("./data")
ML_1M_DIR = DATA_BASE_PATH / "ml-1m"
MOVIES_FILE_NAME = "movies.dat"
RATINGS_FILE_NAME = "ratings.dat"
MOVIES_FILE = ML_1M_DIR / MOVIES_FILE_NAME
RATINGS_FILE = ML_1M_DIR / RATINGS_FILE_NAME

DEFAULT_USERS_TO_SEED = 200
DEFAULT_MAX_RATINGS_PER_USER = 70
DEFAULT_MIN_RATINGS = 20
DEFAULT_SEED = 42

YOUTUBE_VIDEO_IDS = [
    "u31SAHB9hX4",
    "euz-KBBfAAo",
    "6ZfuNTqbHE8",
    "hA6hldpSTF8",
    "QwievZ1Tx-8",
    "EXeTwQWrcwY",
    "YoHD9XEInc0",
    "s7EdQ4FqbhY",
    "5PSNL1qE6VY",
    "KYz2wyBy3kc",
    "RFinNxS5KN4",
    "9ix7TUGVYIo",
    "kXYiU_JCYtU",
    "6hB3S9bIaco",
    "m8e-FF8MsqU",
]

ML_1M_DIR.mkdir(parents=True, exist_ok=True)
movielens_id_to_internal_id_map: Dict[int, int] = {}


async def download_and_extract_movielens_if_needed():
    if MOVIES_FILE.exists() and RATINGS_FILE.exists():
        logger.info(f"MovieLens data files found at {ML_1M_DIR}. Skipping download.")
        return True
    logger.info(f"Attempting to download MovieLens 1M dataset to {ML_1M_DIR}...")
    try:
        response = requests.get(MOVIELENS_1M_URL, stream=True, timeout=120)
        response.raise_for_status()
        with zipfile.ZipFile(BytesIO(response.content)) as z:
            logger.info(f"Extracting necessary files to {ML_1M_DIR}...")
            extracted_something = False
            for member_info in z.infolist():
                file_path_in_zip = Path(member_info.filename)
                if file_path_in_zip.name == MOVIES_FILE_NAME:
                    with z.open(member_info) as source, open(MOVIES_FILE, "wb") as target:
                        target.write(source.read())
                    logger.info(f"Extracted {MOVIES_FILE_NAME}")
                    extracted_something = True
                elif file_path_in_zip.name == RATINGS_FILE_NAME:
                    with z.open(member_info) as source, open(RATINGS_FILE, "wb") as target:
                        target.write(source.read())
                    logger.info(f"Extracted {RATINGS_FILE_NAME}")
                    extracted_something = True
            if not extracted_something:
                logger.warning(f"Could not find {MOVIES_FILE_NAME} or {RATINGS_FILE_NAME} in zip.")
        if not MOVIES_FILE.exists() or not RATINGS_FILE.exists():
            logger.error(f"Download/extraction failed for {ML_1M_DIR}.")
            return False
        logger.info("MovieLens 1M dataset downloaded and extracted successfully.")
        return True
    except Exception as e:
        logger.error(f"Download/extraction error: {e}", exc_info=True)
        return False


async def seed_movies(db: AsyncSession, seed: int = DEFAULT_SEED):
    global movielens_id_to_internal_id_map
    if not MOVIES_FILE.exists():
        logger.error(f"{MOVIES_FILE} not found! Cannot seed movies.")
        return

    count_query = select(func.count()).select_from(Movie.__table__)
    existing_movie_count = (await db.execute(count_query)).scalar_one()
    if existing_movie_count > 0:
        logger.info(f"Movies table has {existing_movie_count} movies. Populating ID map from DB.")
        existing_movies_from_db = await db.execute(
            select(Movie.id, Movie.movie_lens_id).filter(Movie.movie_lens_id.isnot(None))
        )
        for internal_id, ml_id in existing_movies_from_db.all():
            if ml_id is not None:
                movielens_id_to_internal_id_map[ml_id] = internal_id
        return

    movies_df = pd.read_csv(
        MOVIES_FILE,
        sep="::",
        names=["MovieLensID", "Title", "Genres"],
        engine="python",
        encoding="iso-8859-1",
    )
    logger.info(f"Found {len(movies_df)} movies in {MOVIES_FILE_NAME}.")
    created_count = 0
    rng = random.Random(seed)
    shuffled_video_ids = list(YOUTUBE_VIDEO_IDS)
    rng.shuffle(shuffled_video_ids)

    for idx, row_data in movies_df.iterrows():
        movie_lens_id = int(row_data["MovieLensID"])
        video_id_for_url = shuffled_video_ids[idx % len(shuffled_video_ids)]
        dummy_url = f"https://www.youtube.com/watch?v={video_id_for_url}"

        movie_in = MovieCreate(
            title=str(row_data["Title"]),
            genres=str(row_data["Genres"]),
            resource_url=dummy_url,
            movie_lens_id=movie_lens_id,
        )
        try:
            created_movie = await crud.movie.create(db, obj_in=movie_in)
            movielens_id_to_internal_id_map[movie_lens_id] = created_movie.id
            created_count += 1
        except Exception as e:
            logger.error(f"Error creating movie {movie_lens_id}: {e}")
    logger.info(f"Finished seeding movies. {created_count} movies added.")


async def seed_users_and_ratings(
    db: AsyncSession,
    num_users: int = DEFAULT_USERS_TO_SEED,
    full_dataset: bool = False,
    max_ratings_per_user: int = DEFAULT_MAX_RATINGS_PER_USER,
    min_ratings: int = DEFAULT_MIN_RATINGS,
    seed: int = DEFAULT_SEED,
):
    global movielens_id_to_internal_id_map
    user_count_query = select(func.count()).select_from(User.__table__)
    existing_user_count = (await db.execute(user_count_query)).scalar_one()
    if existing_user_count > 0:
        logger.info(f"Users table already contains {existing_user_count} users. Skipping user/rating seed.")
        return

    ratings_df = pd.read_csv(
        RATINGS_FILE,
        sep="::",
        names=["UserID", "MovieLensRatingID", "Rating", "Timestamp"],
        engine="python",
    )

    user_rating_counts = ratings_df["UserID"].value_counts()
    eligible_ml_user_ids = user_rating_counts[user_rating_counts >= min_ratings].index.tolist()
    if not eligible_ml_user_ids:
        logger.warning("No users meet min ratings criterion.")
        return

    rng = random.Random(seed)
    rng.shuffle(eligible_ml_user_ids)

    if full_dataset:
        selected_ml_user_ids = eligible_ml_user_ids
        logger.info(f"Full dataset mode enabled: seeding all {len(selected_ml_user_ids)} eligible users.")
    else:
        selected_ml_user_ids = eligible_ml_user_ids[:num_users]
        logger.info(f"Seeding {len(selected_ml_user_ids)} users (subset mode).")

    # Create users in DB
    ml_user_id_to_db_user_map = {}
    created_user_count = 0
    for ml_uid in selected_ml_user_ids:
        user_in = UserCreate(
            email=f"user{ml_uid}@example.com",
            password=f"pass{ml_uid}",
        )
        try:
            db_user = await crud.user.create(db, obj_in=user_in)
            ml_user_id_to_db_user_map[int(ml_uid)] = db_user
            created_user_count += 1
        except Exception as e:
            logger.error(f"Error creating user {ml_uid}: {e}")

    logger.info(f"Created {created_user_count} users in DB.")
    if not ml_user_id_to_db_user_map:
        return

    # Filter ratings for selected users
    ratings_to_seed_df = ratings_df[ratings_df["UserID"].isin(ml_user_id_to_db_user_map.keys())].copy()

    def sample_group(group_df):
        if full_dataset or max_ratings_per_user <= 0:
            return group_df
        return group_df.sample(n=min(len(group_df), max_ratings_per_user), random_state=seed)

    sampled_dfs = []
    for _, group in ratings_to_seed_df.groupby("UserID"):
        sampled_dfs.append(sample_group(group))

    sampled_ratings_df = pd.concat(sampled_dfs).reset_index(drop=True) if sampled_dfs else pd.DataFrame()
    logger.info(f"Selected {len(sampled_ratings_df)} ratings to insert.")

    seeded_ratings_count = 0
    for _, row in sampled_ratings_df.iterrows():
        try:
            ml_uid = int(row["UserID"])
            ml_movie_id = int(row["MovieLensRatingID"])
            rating_val = float(row["Rating"])
            ts_val = int(row["Timestamp"])
        except Exception as e:
            continue

        db_user = ml_user_id_to_db_user_map.get(ml_uid)
        internal_movie_id = movielens_id_to_internal_id_map.get(ml_movie_id)

        if db_user and internal_movie_id:
            rating_in = RatingCreate(
                movie_id=internal_movie_id,
                rating=rating_val,
                timestamp=ts_val,
            )
            try:
                await crud.rating.create_with_owner(db, obj_in=rating_in, user_id=db_user.id)
                seeded_ratings_count += 1
            except Exception as e:
                pass

    logger.info(f"Finished seeding ratings. {seeded_ratings_count} ratings added.")


async def report_dataset_counts(db: AsyncSession):
    users_cnt = (await db.execute(select(func.count()).select_from(User.__table__))).scalar_one()
    movies_cnt = (await db.execute(select(func.count()).select_from(Movie.__table__))).scalar_one()
    ratings_cnt = (await db.execute(select(func.count()).select_from(Rating.__table__))).scalar_one()

    # Get user sequence counts
    all_ratings = await crud.rating.get_all_ratings_for_training(db)
    user_counts = pd.Series([r.user_id for r in all_ratings]).value_counts()
    eligible_users = (user_counts >= settings.MIN_SEQUENCE_LENGTH).sum()

    # Approximate sliding window examples
    total_examples = sum(max(0, count - 1) for count in user_counts if count >= settings.MIN_SEQUENCE_LENGTH)

    print("\n" + "=" * 60)
    print("  DATABASE SEEDING SUMMARY REPORT")
    print("=" * 60)
    print(f"  Total Users in DB:             {users_cnt:,}")
    print(f"  Total Movies in DB:            {movies_cnt:,}")
    print(f"  Total Ratings in DB:           {ratings_cnt:,}")
    print(f"  Eligible Users (>= {settings.MIN_SEQUENCE_LENGTH} ratings): {eligible_users:,}")
    print(f"  Estimated Training Examples:   {total_examples:,}")
    print("=" * 60 + "\n")


async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_database(
    num_users: int = DEFAULT_USERS_TO_SEED,
    full: bool = False,
    max_ratings: int = DEFAULT_MAX_RATINGS_PER_USER,
    min_ratings: int = DEFAULT_MIN_RATINGS,
    seed: int = DEFAULT_SEED,
):
    await init_db()
    if not await download_and_extract_movielens_if_needed():
        logger.error("Failed to acquire MovieLens data. Aborting seed.")
        return

    global movielens_id_to_internal_id_map
    movielens_id_to_internal_id_map = {}
    async with AsyncSessionLocal() as db:
        await seed_movies(db, seed=seed)
        await seed_users_and_ratings(
            db,
            num_users=num_users,
            full_dataset=full,
            max_ratings_per_user=max_ratings,
            min_ratings=min_ratings,
            seed=seed,
        )
        await report_dataset_counts(db)


def parse_args():
    parser = argparse.ArgumentParser(description="Seed database with MovieLens 1M data")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS_TO_SEED, help="Number of users to seed (default: 200)")
    parser.add_argument("--full", action="store_true", help="Seed full MovieLens 1M dataset")
    parser.add_argument("--max-ratings", type=int, default=DEFAULT_MAX_RATINGS_PER_USER, help="Max ratings sampled per user")
    parser.add_argument("--min-ratings", type=int, default=DEFAULT_MIN_RATINGS, help="Minimum ratings for user consideration")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for reproducibility")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    os.environ.setdefault("KERAS_BACKEND", "tensorflow")
    asyncio.run(
        seed_database(
            num_users=args.users,
            full=args.full,
            max_ratings=args.max_ratings,
            min_ratings=args.min_ratings,
            seed=args.seed,
        )
    )
