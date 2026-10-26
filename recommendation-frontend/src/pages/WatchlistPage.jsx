import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useAppContext } from "../contexts/AppContext";
import ApiService from "../services/ApiService";
import MovieGrid from "../components/Common/MovieGrid";
import LoadingSpinner from "../components/Common/LoadingSpinner";
import RatingModal from "../components/Common/RatingModal";

const WatchlistPage = () => {
  const { token, isAuthenticated } = useAuth();
  const { navigateTo } = useAppContext();

  const [watchlistItems, setWatchlistItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showRatingModalFor, setShowRatingModalFor] = useState(null);

  const fetchWatchlist = useCallback(async () => {
    if (!isAuthenticated || !token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await ApiService.getMyWatchlist(token, 0, 50);
      setWatchlistItems(data || []);
    } catch (err) {
      setError(err.message || "Failed to load watchlist.");
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, token]);

  useEffect(() => {
    fetchWatchlist();
  }, [fetchWatchlist]);

  const handleCardClick = (movieId) => {
    navigateTo("movieDetail", movieId);
  };

  const handleRateMovieClick = (movie) => {
    setShowRatingModalFor(movie);
  };

  const handleRatingModalClose = () => {
    setShowRatingModalFor(null);
  };

  if (!isAuthenticated) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center space-y-4">
        <h1 className="font-['Jost',sans-serif] text-2xl font-bold uppercase tracking-wider text-[#141414]">
          Your Watchlist
        </h1>
        <p className="text-sm text-[#5E5A52] leading-relaxed font-['Jost',sans-serif]">
          Log in or register an account to save films to your personal watchlist and track cinema you want to watch.
        </p>
        <div className="pt-2">
          <button
            type="button"
            onClick={() => navigateTo("login")}
            className="px-6 py-3 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
          >
            Sign In to View Watchlist
          </button>
        </div>
      </div>
    );
  }

  const movies = watchlistItems
    .map((item) => item.movie)
    .filter(Boolean);

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-4 border-b border-[#D9D3C7]">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-['Jost',sans-serif] font-bold text-2xl sm:text-3xl uppercase tracking-[0.1em] text-[#141414]">
              My Watchlist
            </h1>
            <span className="px-2 py-0.5 text-[10px] font-['Jost',sans-serif] font-bold uppercase tracking-wider bg-[#141414] text-white">
              {watchlistItems.length} Saved
            </span>
          </div>
          <p className="text-xs text-[#5E5A52] font-medium mt-1">
            Titles you have saved for future viewing
          </p>
        </div>

        <button
          type="button"
          onClick={() => navigateTo("home")}
          className="text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#C8412B] hover:underline cursor-pointer"
        >
          Explore Catalogue &rarr;
        </button>
      </div>

      {loading ? (
        <LoadingSpinner text="Retrieving your watchlist..." />
      ) : movies.length === 0 ? (
        <div className="border border-[#D9D3C7] bg-white p-12 text-center max-w-md mx-auto space-y-3">
          <h2 className="font-['Jost',sans-serif] font-bold text-base uppercase tracking-wider text-[#141414]">
            Your Watchlist is Empty
          </h2>
          <p className="text-xs sm:text-sm text-[#5E5A52] leading-relaxed font-['Jost',sans-serif]">
            Browse the discovery catalogue and click "+ Watchlist" on any title to save films here.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={() => navigateTo("home")}
              className="px-6 py-2.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
            >
              Browse Catalogue
            </button>
          </div>
        </div>
      ) : (
        <MovieGrid
          movies={movies}
          loading={loading}
          error={error}
          onCardClick={handleCardClick}
          onRateMovieClick={handleRateMovieClick}
          isAuthenticated={isAuthenticated}
        />
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

export default WatchlistPage;
