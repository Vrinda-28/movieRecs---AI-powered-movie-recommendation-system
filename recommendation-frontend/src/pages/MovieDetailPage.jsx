import React, { useState, useEffect, useCallback, useRef } from "react";
import { useAppContext } from "../contexts/AppContext";
import { useAuth } from "../contexts/AuthContext";
import ApiService from "../services/ApiService";
import LoadingSpinner from "../components/Common/LoadingSpinner";
import PosterImage from "../components/Common/PosterImage";
import RatingStars from "../components/Common/RatingStars";
import RatingModal from "../components/Common/RatingModal";
import WatchlistButton from "../components/Common/WatchlistButton";
import ReviewForm from "../components/Reviews/ReviewForm";
import ReviewCard from "../components/Reviews/ReviewCard";
import TrailerPanel from "../components/Common/TrailerPanel";
import RelatedRow from "../components/Common/RelatedRow";
import AskMoviePanel from "../components/Common/AskMoviePanel";
import { parseMovieTitle, parseGenres } from "../utils/movieTitle";
import { useMovieMedia, backdropUrl } from "../services/movieMedia";
import {
  ArrowLeft,
  Star,
  Film,
  Play,
  Users,
  Info,
  MessageSquare,
  Clock,
  Calendar,
} from "lucide-react";

/**
 * Editorial MovieDetailPage modeled on the movie-profile reference:
 * 1. Wide backdrop with Back navigation control
 * 2. White content band: Tracked title + year, pipe genres, black stars, meta columns, hairline rule
 * 3. Two-column body:
 *    - Left: Tall portrait poster (w500), Director/Cast credits, real Plot with read-more toggle, actions
 *    - Right: Circular coral icon tabs, TrailerPanel with click-to-load
 * 4. Tagline quote band (omitted if missing)
 * 5. Reviews section with privacy and validation
 * 6. Full-width coral RELATED MOVIES carousel
 */
const MovieDetailPage = () => {
  const { selectedMovieId, navigateTo, previousPageInfo, showGlobalMessage } =
    useAppContext();
  const { token, isAuthenticated, currentUser, isAdmin } = useAuth();

  const [movie, setMovie] = useState(null);
  const [userRating, setUserRating] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [loadingReviews, setLoadingReviews] = useState(false);
  const [reviewsPage, setReviewsPage] = useState(0);
  const [hasMoreReviews, setHasMoreReviews] = useState(false);
  const REVIEWS_PER_PAGE = 5;
  const [showReviewForm, setShowReviewForm] = useState(false);

  const [relatedMovies, setRelatedMovies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showRatingModalFor, setShowRatingModalFor] = useState(null);
  const [isPlotExpanded, setIsPlotExpanded] = useState(false);

  // De-duplication ref for logging VIEW interaction
  const loggedViewRef = useRef(null);

  const media = useMovieMedia(movie);

  const fetchReviewsPage = useCallback(
    async (page = 0) => {
      if (!selectedMovieId) return;
      setLoadingReviews(true);
      try {
        const data = await ApiService.getMovieReviews(
          selectedMovieId,
          page * REVIEWS_PER_PAGE,
          REVIEWS_PER_PAGE + 1,
        );
        if (data && data.length > REVIEWS_PER_PAGE) {
          setHasMoreReviews(true);
          setReviews(data.slice(0, REVIEWS_PER_PAGE));
        } else {
          setHasMoreReviews(false);
          setReviews(data || []);
        }
        setReviewsPage(page);
      } catch {
        setReviews([]);
        setHasMoreReviews(false);
      } finally {
        setLoadingReviews(false);
      }
    },
    [selectedMovieId],
  );

  const fetchMovieDetails = useCallback(async () => {
    if (!selectedMovieId) {
      navigateTo("home");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const movieData = await ApiService.getMovieById(selectedMovieId, token);
      setMovie(movieData);

      // Log VIEW interaction once per visit
      if (loggedViewRef.current !== selectedMovieId) {
        loggedViewRef.current = selectedMovieId;
        ApiService.logInteraction(
          { movie_id: selectedMovieId, event_type: "VIEW" },
          token,
        );
      }

      // Fetch user's rating for this movie if authenticated
      if (token && isAuthenticated) {
        try {
          const userRatings = await ApiService.getMyRatings(token, 0, 100);
          if (userRatings && userRatings.length > 0) {
            const matched = userRatings.find((r) => r.movie_id === selectedMovieId);
            if (matched) setUserRating(matched.rating);
          }
        } catch {
          // Silent fallback
        }
      }

      // Fetch reviews
      fetchReviewsPage(0);

      // Fetch Related Movies based on the film's first genre sorted by num_ratings
      const genresList = parseGenres(movieData?.genres);
      if (genresList.length > 0) {
        const primaryGenre = genresList[0];
        try {
          const genreMovies = await ApiService.getMovies(0, 60, token, null, primaryGenre);
          if (genreMovies && genreMovies.length > 0) {
            setRelatedMovies(genreMovies);
          }
        } catch {
          setRelatedMovies([]);
        }
      }
    } catch (err) {
      setError(
        err.status === 404
          ? "Movie not found (404). This title may have been removed or does not exist."
          : err.message || "Failed to load movie details.",
      );
    } finally {
      setLoading(false);
    }
  }, [selectedMovieId, token, isAuthenticated, navigateTo, fetchReviewsPage]);

  useEffect(() => {
    fetchMovieDetails();
    setIsPlotExpanded(false);
  }, [fetchMovieDetails]);

  const handleBackNavigation = () => {
    navigateTo(previousPageInfo.page || "home", previousPageInfo.movieId);
  };

  const handleRateMovieClick = () => {
    if (!isAuthenticated) {
      showGlobalMessage("Please log in to rate movies.", "error");
      navigateTo("login");
      return;
    }
    setShowRatingModalFor({ ...movie, user_rating: userRating });
  };

  const handleRatingModalClose = () => {
    setShowRatingModalFor(null);
    if (selectedMovieId) {
      fetchMovieDetails();
    }
  };

  const handleCreateReview = async (text) => {
    if (!isAuthenticated) {
      showGlobalMessage("Please log in to write a review.", "error");
      navigateTo("login");
      return;
    }
    try {
      await ApiService.createReview({ movie_id: selectedMovieId, text }, token);
      showGlobalMessage("Review published successfully!", "success");
      setShowReviewForm(false);
      fetchReviewsPage(0);
    } catch (err) {
      showGlobalMessage(err.message || "Failed to post review", "error");
    }
  };

  const handleUpdateReview = async (reviewId, newText) => {
    try {
      await ApiService.updateReview(reviewId, { text: newText }, token);
      showGlobalMessage("Review updated successfully!", "success");
      fetchReviewsPage(reviewsPage);
    } catch (err) {
      showGlobalMessage(err.message || "Failed to update review", "error");
      throw err;
    }
  };

  const handleDeleteReview = async (reviewId) => {
    try {
      await ApiService.deleteReview(reviewId, token);
      showGlobalMessage("Review removed.", "success");
      fetchReviewsPage(reviewsPage);
    } catch (err) {
      showGlobalMessage(err.message || "Failed to delete review", "error");
    }
  };

  if (loading) return <LoadingSpinner text="Loading film profile…" />;

  if (error || !movie) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center space-y-4">
        <h1 className="font-['Jost',sans-serif] text-xl font-bold uppercase tracking-wider text-[#141414]">
          {error || "Movie Not Available"}
        </h1>
        <button
          type="button"
          onClick={handleBackNavigation}
          className="px-6 py-2.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
        >
          Return to Catalogue
        </button>
      </div>
    );
  }

  const { title: cleanTitle, year } = parseMovieTitle(movie.title);
  const genres = parseGenres(movie.genres);
  const backdrop = backdropUrl(media, 1280);

  // Tab anchors
  const scrollToSection = (id) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <article className="w-full bg-[#FAF7F2] text-[#141414]" key={movie.id}>
      {/* ======================================================================= */}
      {/* 1. CINEMATIC BACKDROP BANNER                                            */}
      {/* ======================================================================= */}
      <div className="relative w-full aspect-[21/9] min-h-[260px] max-h-[460px] bg-[#141414] overflow-hidden border-b border-[#D9D3C7]">
        {backdrop ? (
          <>
            <img
              src={backdrop}
              alt=""
              fetchPriority="high"
              className="w-full h-full object-cover object-top opacity-50"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-[#141414] via-[#141414]/40 to-black/30" />
          </>
        ) : (
          <div className="w-full h-full bg-[#141414]" />
        )}

        {/* Back Navigation Button */}
        <div className="absolute top-6 left-4 sm:left-8 z-20">
          <button
            type="button"
            onClick={handleBackNavigation}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 bg-black/60 hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest backdrop-blur-xs transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
            aria-label="Back to previous page"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back</span>
          </button>
        </div>
      </div>

      {/* ======================================================================= */}
      {/* 2. WHITE EDITORIAL HEADER BAND                                          */}
      {/* ======================================================================= */}
      <section className="bg-white border-b border-[#D9D3C7]" aria-label="Movie header">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10">
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6">
            {/* Title, Year, Genres, Community Stars */}
            <div className="space-y-3">
              <h1 className="font-['Jost',sans-serif] font-black text-2xl sm:text-3xl md:text-4xl uppercase tracking-[0.1em] text-[#141414] leading-tight">
                {cleanTitle} {year && <span className="text-[#5E5A52] font-normal text-xl sm:text-2xl">({year})</span>}
              </h1>

              {/* Genres separated by thin vertical bars */}
              <div className="flex flex-wrap items-center gap-2 text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#5E5A52]">
                {genres.map((g, idx) => (
                  <React.Fragment key={g}>
                    {idx > 0 && <span className="text-[#D9D3C7]">|</span>}
                    <span>{g}</span>
                  </React.Fragment>
                ))}
              </div>

              {/* Star row in near-black ink */}
              <div className="pt-1 flex items-center gap-3">
                <RatingStars
                  rating={movie.average_rating}
                  numRatings={movie.num_ratings}
                  size="md"
                  theme="ink"
                />
                {movie.num_ratings > 0 && (
                  <span className="text-xs text-[#5E5A52] font-medium font-['Jost',sans-serif]">
                    avg from {movie.num_ratings.toLocaleString()} members
                  </span>
                )}
              </div>
            </div>

            {/* Meta columns (Runtime, Release Date, Community Rating, Ratings Count) */}
            <div className="flex flex-wrap items-center gap-4 sm:gap-6 pt-4 lg:pt-0 border-t lg:border-t-0 border-[#D9D3C7]/60 text-xs font-['Jost',sans-serif]">
              {media?.runtime && (
                <div className="space-y-0.5">
                  <span className="block text-[11px] font-bold uppercase tracking-wider text-[#5E5A52]">
                    Runtime
                  </span>
                  <span className="font-bold text-[#141414] tabular-nums">
                    {media.runtime} min
                  </span>
                </div>
              )}

              {media?.releaseDate && (
                <div className="space-y-0.5">
                  <span className="block text-[11px] font-bold uppercase tracking-wider text-[#5E5A52]">
                    Release
                  </span>
                  <span className="font-bold text-[#141414]">
                    {new Date(media.releaseDate).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                </div>
              )}

              <div className="space-y-0.5">
                <span className="block text-[11px] font-bold uppercase tracking-wider text-[#5E5A52]">
                  Rating
                </span>
                <span className="font-bold text-[#141414] tabular-nums">
                  {movie.average_rating ? movie.average_rating.toFixed(2) : "—"} / 5.0
                </span>
              </div>

              <div className="space-y-0.5">
                <span className="block text-[11px] font-bold uppercase tracking-wider text-[#5E5A52]">
                  Votes
                </span>
                <span className="font-bold text-[#141414] tabular-nums">
                  {(movie.num_ratings || 0).toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ======================================================================= */}
      {/* 3. TWO-COLUMN BODY                                                      */}
      {/* ======================================================================= */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14">
          {/* ── LEFT COLUMN (Poster, Quick Meta, Actions) ── */}
          <div className="lg:col-span-5 space-y-8">
            {/* Portrait Poster (w500) */}
            <div className="w-full max-w-sm mx-auto lg:mx-0 aspect-[2/3] border border-[#D9D3C7] shadow-lg bg-[#EFEAE1] overflow-hidden">
              <PosterImage
                movie={movie}
                title={movie.title}
                genres={movie.genres}
                priority={true}
                targetWidth={500}
                className="w-full h-full"
              />
            </div>

            {/* Quick Metadata Sidebar */}
            <div className="border border-[#D9D3C7] bg-[#FAF7F2] p-5 space-y-3 font-['Jost',sans-serif]">
              <div className="flex items-center justify-between pb-2 border-b border-[#D9D3C7] text-xs">
                <span className="text-[#5E5A52] uppercase tracking-wider font-bold">Release</span>
                <span className="font-bold text-[#141414]">{year || "—"}</span>
              </div>
              <div className="flex items-center justify-between pb-2 border-b border-[#D9D3C7] text-xs">
                <span className="text-[#5E5A52] uppercase tracking-wider font-bold">Genre</span>
                <span className="font-bold text-[#141414] truncate max-w-[60%] text-right">
                  {genres.join(", ") || "—"}
                </span>
              </div>
              <div className="flex items-center justify-between pb-2 border-b border-[#D9D3C7] text-xs">
                <span className="text-[#5E5A52] uppercase tracking-wider font-bold">Score</span>
                <span className="font-bold text-[#141414]">
                  {movie.average_rating ? movie.average_rating.toFixed(2) : "—"} / 5.0
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-[#5E5A52] uppercase tracking-wider font-bold">Votes</span>
                <span className="font-bold text-[#141414]">
                  {(movie.num_ratings || 0).toLocaleString()}
                </span>
              </div>
            </div>

            {/* Action Buttons: Rate Movie & Watchlist */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <button
                type="button"
                onClick={handleRateMovieClick}
                className="px-5 py-3 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors flex items-center gap-2 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
              >
                <Star className="w-3.5 h-3.5 fill-white" />
                <span>{userRating ? `Your Rating: ${userRating}★` : "Rate Film"}</span>
              </button>

              <WatchlistButton movieId={movie.id} />
            </div>
          </div>

          {/* ── RIGHT COLUMN (Navigation Tabs, Overview, Trailer, Reviews) ── */}
          <div className="lg:col-span-7 space-y-10">
            {/* Circular Coral Navigation Tabs */}
            <div className="flex flex-wrap items-center justify-start sm:justify-between gap-4 pb-4 border-b border-[#D9D3C7]">
              <button
                type="button"
                onClick={() => scrollToSection("overview-section")}
                className="flex flex-col items-center gap-1.5 group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
              >
                <div className="w-12 h-12 rounded-full bg-[#C8412B] group-hover:bg-[#A8321F] text-white flex items-center justify-center transition-transform group-hover:scale-105 shadow-sm">
                  <Film className="w-5 h-5" />
                </div>
                <span className="text-[10px] font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#141414]">
                  Overview
                </span>
              </button>

              <button
                type="button"
                onClick={() => scrollToSection("trailer-section")}
                className="flex flex-col items-center gap-1.5 group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
              >
                <div className="w-12 h-12 rounded-full bg-[#C8412B] group-hover:bg-[#A8321F] text-white flex items-center justify-center transition-transform group-hover:scale-105 shadow-sm">
                  <Play className="w-5 h-5 fill-white translate-x-0.5" />
                </div>
                <span className="text-[10px] font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#141414]">
                  Trailer
                </span>
              </button>

              <button
                type="button"
                onClick={() => scrollToSection("reviews")}
                className="flex flex-col items-center gap-1.5 group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
              >
                <div className="w-12 h-12 rounded-full bg-[#C8412B] group-hover:bg-[#A8321F] text-white flex items-center justify-center transition-transform group-hover:scale-105 shadow-sm">
                  <MessageSquare className="w-5 h-5" />
                </div>
                <span className="text-[10px] font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#141414]">
                  Reviews
                </span>
              </button>
            </div>

            {/* 1. Overview Section */}
            <section className="space-y-4" id="overview-section" aria-label="Movie overview and details">
              <div className="space-y-1">
                <span className="block text-[11px] font-['Jost',sans-serif] font-bold uppercase tracking-widest text-[#5E5A52]">
                  SYNOPSIS & CREDITS
                </span>
                <h2 className="font-['Cormorant_Garamond',serif] text-2xl sm:text-3xl font-semibold text-[#141414]">
                  Overview
                </h2>
              </div>

              {/* Tagline if available */}
              {media?.tagline && (
                <p className="font-['Cormorant_Garamond',serif] text-xl italic text-[#5E5A52] leading-snug">
                  "{media.tagline}"
                </p>
              )}

              {/* Synopsis paragraph */}
              <p
                className={`font-['Jost',sans-serif] text-sm sm:text-base text-[#141414] leading-relaxed ${
                  isPlotExpanded ? "" : "line-clamp-6"
                }`}
              >
                {media?.overview ||
                  `${cleanTitle} is a ${genres.join(" and ")} feature released in ${
                    year || "the MovieLens archive"
                  }. Preserved in the MovieLens catalog, it holds an average community rating of ${
                    movie.average_rating ? movie.average_rating.toFixed(2) : "—"
                  } / 5.0 across ${(movie.num_ratings || 0).toLocaleString()} member ratings.`}
              </p>

              {(media?.overview?.length > 250 || (!media?.overview && cleanTitle.length > 50)) && (
                <button
                  type="button"
                  onClick={() => setIsPlotExpanded(!isPlotExpanded)}
                  className="px-4 py-2 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
                >
                  {isPlotExpanded ? "READ LESS" : "READ MORE"}
                </button>
              )}

              {/* Credits Block (Director & Cast) */}
              {(media?.director?.length > 0 || media?.cast?.length > 0) && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-[#D9D3C7]" id="cast">
                  {media.director && media.director.length > 0 && (
                    <div>
                      <span className="block text-[11px] font-['Jost',sans-serif] font-bold uppercase tracking-widest text-[#5E5A52]">
                        DIRECTOR
                      </span>
                      <p className="font-['Jost',sans-serif] font-bold text-sm text-[#141414] mt-0.5">
                        {media.director.join(", ")}
                      </p>
                    </div>
                  )}

                  {media.cast && media.cast.length > 0 && (
                    <div>
                      <span className="block text-[11px] font-['Jost',sans-serif] font-bold uppercase tracking-widest text-[#5E5A52]">
                        KEY CAST
                      </span>
                      <p className="font-['Jost',sans-serif] text-sm text-[#141414] mt-0.5 leading-relaxed">
                        {media.cast.slice(0, 5).map((c) => c.name).join(", ")}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </section>

            {/* 2. Trailer Panel (strictly movie-specific, keyed to reset state on navigate) */}
            <TrailerPanel key={movie.id} movie={movie} media={media} />

            {/* 3. Grounded AI Q&A Panel */}
            <AskMoviePanel
              key={movie.id}
              movieId={movie.id}
              movieTitle={cleanTitle}
              isAuthenticated={isAuthenticated}
              token={token}
              navigateTo={navigateTo}
              onMovieClick={(id) => {
                navigateTo("movieDetail", id);
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            />

            {/* Reviews Section */}
            <section className="space-y-6 pt-6 border-t border-[#D9D3C7]" id="reviews" aria-label="Member reviews">
              <div className="flex items-center justify-between pb-2 border-b border-[#D9D3C7]">
                <h3 className="font-['Jost',sans-serif] font-bold text-sm uppercase tracking-widest text-[#141414]">
                  MEMBER REVIEWS ({reviews.length})
                </h3>

                {isAuthenticated && (
                  <button
                    type="button"
                    onClick={() => setShowReviewForm(!showReviewForm)}
                    className="text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#C8412B] hover:underline cursor-pointer"
                  >
                    {showReviewForm ? "Close Form" : "+ Write Review"}
                  </button>
                )}
              </div>

              {/* Review Form */}
              {showReviewForm && (
                <div className="p-5 bg-white border border-[#D9D3C7]">
                  <ReviewForm
                    onSubmit={handleCreateReview}
                    onCancel={() => setShowReviewForm(false)}
                  />
                </div>
              )}

              {/* Reviews List */}
              {loadingReviews && (
                <div className="text-center py-6 text-xs uppercase tracking-wider text-[#5E5A52]">
                  Loading member perspectives...
                </div>
              )}

              {!loadingReviews && reviews.length === 0 && (
                <div className="p-8 border border-[#D9D3C7] bg-white text-center">
                  <p className="font-['Jost',sans-serif] text-sm text-[#5E5A52]">
                    Be the first to review {cleanTitle}.
                  </p>
                  {!isAuthenticated && (
                    <button
                      type="button"
                      onClick={() => navigateTo("login")}
                      className="mt-3 text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#C8412B] hover:underline cursor-pointer"
                    >
                      Log in to leave a review
                    </button>
                  )}
                </div>
              )}

              {!loadingReviews && reviews.length > 0 && (
                <div className="space-y-4">
                  {reviews.map((r) => (
                    <ReviewCard
                      key={r.id}
                      review={r}
                      currentUserId={currentUser?.id}
                      currentUserEmail={currentUser?.email}
                      isAdmin={isAdmin}
                      onUpdate={handleUpdateReview}
                      onDelete={handleDeleteReview}
                    />
                  ))}
                </div>
              )}

              {/* Reviews pagination */}
              {hasMoreReviews && (
                <div className="text-center pt-2">
                  <button
                    type="button"
                    onClick={() => fetchReviewsPage(reviewsPage + 1)}
                    className="px-5 py-2 bg-white border border-[#D9D3C7] hover:border-[#141414] text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#141414] transition-colors cursor-pointer"
                  >
                    Older Reviews
                  </button>
                </div>
              )}
            </section>
          </div>
        </div>
      </main>

      {/* ======================================================================= */}
      {/* 4. LIGHT GREY QUOTE BAND (Tagline from TMDB manifest)                  */}
      {/* ======================================================================= */}
      {media?.tagline && (
        <section className="w-full bg-[#EFEAE1] border-y border-[#D9D3C7] py-10 px-4 text-center my-6">
          <div className="max-w-3xl mx-auto space-y-2">
            <blockquote className="font-['Cormorant_Garamond',serif] italic text-xl sm:text-2xl text-[#141414] leading-relaxed">
              "{media.tagline}"
            </blockquote>
            <cite className="block font-['Jost',sans-serif] text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5E5A52] not-italic">
              Tagline
            </cite>
          </div>
        </section>
      )}

      {/* ======================================================================= */}
      {/* 5. FULL-WIDTH CORAL RELATED MOVIES BAND                                 */}
      {/* ======================================================================= */}
      <RelatedRow
        movies={relatedMovies}
        genre={genres[0] || ""}
        currentMovieId={movie.id}
        onMovieClick={(id) => {
          navigateTo("movieDetail", id);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
      />

      {/* Rating Modal */}
      <RatingModal
        movie={showRatingModalFor}
        show={Boolean(showRatingModalFor)}
        onClose={handleRatingModalClose}
        token={token}
      />
    </article>
  );
};

export default MovieDetailPage;
