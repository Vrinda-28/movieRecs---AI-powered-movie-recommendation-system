import React, { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useAppContext } from "../contexts/AppContext";
import ApiService from "../services/ApiService";
import MovieCard from "../components/Common/MovieCard";
import LoadingSpinner from "../components/Common/LoadingSpinner";
import RatingModal from "../components/Common/RatingModal";
import { Sparkles, Star } from "lucide-react";

const MIN_RATINGS_FOR_MODEL = 3;

// In-memory session cache for movie details (average_rating, num_ratings)
const movieDetailsCache = new Map();

/**
 * Editorial RecommendationsPage:
 * - Truthful banner reflecting whether items are GRU4Rec sequential recommendations or popularity fallback
 * - Per-item badges (coral "For you" vs neutral "Popular pick")
 * - In-memory cached ratings enrichment for visible items
 */
const RecommendationsPage = () => {
  const [recommendations, setRecommendations] = useState([]);
  const [enrichedRatings, setEnrichedRatings] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { token, isAuthenticated } = useAuth();
  const { navigateTo, showGlobalMessage } = useAppContext();
  const [showRatingModalFor, setShowRatingModalFor] = useState(null);

  const isFetchingDetails = useRef(false);

  const fetchRecommendations = useCallback(() => {
    if (!isAuthenticated || !token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    ApiService.getMyRecommendations(token, 20)
      .then((data) => {
        setRecommendations(data || []);
      })
      .catch((err) => {
        if (err.isNetworkError) {
          setError("Cannot reach recommendation service. Verify backend is running.");
        } else {
          setError(err.message || "Failed to fetch recommendations.");
        }
      })
      .finally(() => setLoading(false));
  }, [token, isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setLoading(false);
      showGlobalMessage("Please log in to see recommendations.", "error");
      navigateTo("login");
      return;
    }
    fetchRecommendations();
  }, [isAuthenticated, fetchRecommendations, navigateTo, showGlobalMessage]);

  // Enrich visible items lacking average_rating/num_ratings via bounded parallel lookup
  useEffect(() => {
    if (!recommendations.length || isFetchingDetails.current) return;

    const visibleItems = recommendations.slice(0, 12);
    const needLookup = visibleItems.filter((item) => {
      const id = item.movie_id || item.id;
      return (
        (item.average_rating === undefined || item.num_ratings === undefined) &&
        !movieDetailsCache.has(id)
      );
    });

    if (!needLookup.length) {
      // Pull already cached details into state if needed
      const cachedUpdates = {};
      visibleItems.forEach((item) => {
        const id = item.movie_id || item.id;
        if (movieDetailsCache.has(id)) {
          cachedUpdates[id] = movieDetailsCache.get(id);
        }
      });
      if (Object.keys(cachedUpdates).length > 0) {
        setEnrichedRatings((prev) => ({ ...prev, ...cachedUpdates }));
      }
      return;
    }

    isFetchingDetails.current = true;
    Promise.all(
      needLookup.map(async (item) => {
        const id = item.movie_id || item.id;
        try {
          const detail = await ApiService.getMovieById(id, token);
          if (detail) {
            const entry = {
              average_rating: detail.average_rating,
              num_ratings: detail.num_ratings,
            };
            movieDetailsCache.set(id, entry);
            return { id, entry };
          }
        } catch {
          // Degrade gracefully
        }
        return null;
      }),
    ).then((results) => {
      isFetchingDetails.current = false;
      const updates = {};
      results.forEach((res) => {
        if (res) updates[res.id] = res.entry;
      });
      if (Object.keys(updates).length > 0) {
        setEnrichedRatings((prev) => ({ ...prev, ...updates }));
      }
    });
  }, [recommendations, token]);

  const handleCardClick = (movieId) => navigateTo("movieDetail", movieId);

  const handleRateMovieClick = (movie) => {
    if (!isAuthenticated) {
      showGlobalMessage("Please log in to rate movies.", "error");
      navigateTo("login");
      return;
    }
    setShowRatingModalFor(movie);
  };

  const handleRatingModalClose = () => {
    setShowRatingModalFor(null);
    fetchRecommendations();
  };

  if (loading) return <LoadingSpinner text="Fetching your recommendations…" />;

  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center space-y-4">
        <h1 className="font-['Jost',sans-serif] text-xl font-bold uppercase tracking-wider text-[#141414]">
          Recommendations Unavailable
        </h1>
        <p className="text-sm text-[#5E5A52] leading-relaxed">{error}</p>
        <button
          type="button"
          onClick={fetchRecommendations}
          className="px-6 py-2.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
        >
          Try Again
        </button>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  const hasPersonalized = recommendations.some((r) => r.is_personalized === true);
  const userRatingCount = recommendations.length > 0 ? recommendations[0].user_rating_count : 0;
  const ratingsNeeded = Math.max(0, MIN_RATINGS_FOR_MODEL - (userRatingCount || 0));

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 space-y-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-4 border-b border-[#D9D3C7]">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-['Jost',sans-serif] font-bold text-2xl sm:text-3xl uppercase tracking-[0.1em] text-[#141414]">
              {hasPersonalized ? "Recommended For You" : "Popular Recommendations"}
            </h1>
            <span className="px-2 py-0.5 text-[10px] font-['Jost',sans-serif] font-bold uppercase tracking-wider bg-[#141414] text-white">
              {hasPersonalized ? "Sequential GRU4Rec" : "Popularity Baseline"}
            </span>
          </div>
          <p className="text-xs text-[#5E5A52] font-medium mt-1.5">
            {hasPersonalized
              ? "Sequential recommendations modeled from your chronological rating history."
              : "Popular community titles. Rate more movies to activate personalized sequential recommendations."}
          </p>
        </div>

        <button
          type="button"
          onClick={() => navigateTo("onboarding")}
          className="px-5 py-2.5 bg-white border border-[#D9D3C7] hover:border-[#141414] text-[#141414] text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider transition-colors cursor-pointer self-start sm:self-auto"
        >
          + Rate More Movies
        </button>
      </div>

      {/* Truthfulness Banner */}
      {hasPersonalized ? (
        <div className="p-6 bg-white border border-[#D9D3C7] space-y-2">
          <div className="flex items-start gap-3">
            <Sparkles className="w-5 h-5 text-[#C8412B] flex-shrink-0 mt-0.5" />
            <div>
              <h2 className="font-['Jost',sans-serif] font-bold text-sm uppercase tracking-wider text-[#141414]">
                Personalized by your rating history
              </h2>
              <p className="text-xs text-[#5E5A52] leading-relaxed mt-1 font-['Jost',sans-serif]">
                Your rating sequence was processed through the GRU4Rec sequential model to retrieve candidate films. Titles tagged <strong className="text-[#C8412B]">For you</strong> reflect personalized inference; any titles tagged <strong className="text-[#141414]">Popular pick</strong> represent popularity backfill.
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-6 bg-[#EFEAE1] border border-[#D9D3C7] space-y-2">
          <div className="flex items-start gap-3">
            <Star className="w-5 h-5 text-[#C8412B] flex-shrink-0 mt-0.5 fill-[#C8412B]" />
            <div>
              <h2 className="font-['Jost',sans-serif] font-bold text-sm uppercase tracking-wider text-[#141414]">
                Popular picks — personalization unlocks soon
              </h2>
              <p className="text-xs text-[#5E5A52] leading-relaxed mt-1 font-['Jost',sans-serif]">
                You have rated <strong className="text-[#141414]">{userRatingCount || 0} movie{userRatingCount === 1 ? "" : "s"}</strong>. Rate <strong className="text-[#C8412B]">{ratingsNeeded} more</strong> to reach the sequence threshold ({MIN_RATINGS_FOR_MODEL}) required by the GRU4Rec sequential model.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {recommendations.length === 0 && !loading && (
        <div className="border border-[#D9D3C7] bg-white p-12 text-center space-y-4">
          <h2 className="font-['Jost',sans-serif] font-bold text-base uppercase tracking-wider text-[#141414]">
            No recommendations generated
          </h2>
          <p className="text-sm text-[#5E5A52] max-w-md mx-auto font-['Jost',sans-serif]">
            Rate movies in the discovery catalogue or complete onboarding to build your sequential profile.
          </p>
          <button
            type="button"
            onClick={() => navigateTo("onboarding")}
            className="px-6 py-3 bg-[#C8412B] hover:bg-[#A8321F] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
          >
            Start Onboarding
          </button>
        </div>
      )}

      {/* Grid of recommendations with rank numerals */}
      {recommendations.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 sm:gap-6">
          {recommendations.map((rec, idx) => {
            const id = rec.movie_id || rec.id;
            const enriched = enrichedRatings[id];

            const movieObj = {
              ...rec,
              id,
              average_rating: enriched ? enriched.average_rating : rec.average_rating,
              num_ratings: enriched ? enriched.num_ratings : rec.num_ratings,
            };

            return (
              <MovieCard
                key={`${id}-${idx}`}
                movie={movieObj}
                rank={idx + 1}
                onCardClick={handleCardClick}
                onRateMovieClick={handleRateMovieClick}
                isAuthenticated={isAuthenticated}
              />
            );
          })}
        </div>
      )}

      {/* Rating Modal */}
      <RatingModal
        movie={showRatingModalFor}
        show={Boolean(showRatingModalFor)}
        onClose={handleRatingModalClose}
        token={token}
      />
    </div>
  );
};

export default RecommendationsPage;
