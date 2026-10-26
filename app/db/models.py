from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)

    ratings = relationship(
        "Rating", back_populates="user", cascade="all, delete-orphan"
    )
    reviews = relationship(
        "Review", back_populates="user", cascade="all, delete-orphan"
    )
    watchlist = relationship(
        "Watchlist", back_populates="user", cascade="all, delete-orphan"
    )
    interactions = relationship(
        "Interaction", back_populates="user", cascade="all, delete-orphan"
    )


class Movie(Base):
    __tablename__ = "movies"

    title = Column(String, index=True, nullable=False)
    genres = Column(String, nullable=True)
    resource_url = Column(String, nullable=True)
    movie_lens_id = Column(Integer, unique=True, nullable=True, index=True)

    ratings = relationship(
        "Rating", back_populates="movie", cascade="all, delete-orphan"
    )
    reviews = relationship(
        "Review", back_populates="movie", cascade="all, delete-orphan"
    )
    watchlist = relationship(
        "Watchlist", back_populates="movie", cascade="all, delete-orphan"
    )
    interactions = relationship(
        "Interaction", back_populates="movie", cascade="all, delete-orphan"
    )


class Rating(Base):
    __tablename__ = "ratings"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)
    rating = Column(Float, nullable=False)
    timestamp = Column(Integer, nullable=False, index=True)

    user = relationship("User", back_populates="ratings")
    movie = relationship("Movie", back_populates="ratings")


class Review(Base):
    """User review for a movie. Enforces single review per user per movie."""

    __tablename__ = "reviews"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)

    user = relationship("User", back_populates="reviews")
    movie = relationship("Movie", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_user_movie_review"),
    )


class Watchlist(Base):
    """User watchlist item. Enforces uniqueness per user and movie."""

    __tablename__ = "watchlist"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)

    user = relationship("User", back_populates="watchlist")
    movie = relationship("Movie", back_populates="watchlist")

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_user_movie_watchlist"),
    )


class Interaction(Base):
    """
    Logs user interactions (VIEW, RATE, REVIEW, WATCHLIST_ADD, WATCHLIST_REMOVE)
    with strict server timestamping. Becomes future training data upon retraining.
    """

    __tablename__ = "interactions"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)
    event_type = Column(
        String(50), nullable=False
    )  # VIEW, RATE, REVIEW, WATCHLIST_ADD, WATCHLIST_REMOVE

    user = relationship("User", back_populates="interactions")
    movie = relationship("Movie", back_populates="interactions")

    __table_args__ = (Index("ix_interactions_user_created", "user_id", "created_at"),)
