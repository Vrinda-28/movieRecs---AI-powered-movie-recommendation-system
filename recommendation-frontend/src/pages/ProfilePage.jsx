import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useAppContext } from "../contexts/AppContext";
import ApiService from "../services/ApiService";
import LoadingSpinner from "../components/Common/LoadingSpinner";
import RatingStars from "../components/Common/RatingStars";
import MovieCard from "../components/Common/MovieCard";

const ProfilePage = () => {
  const { token, isAuthenticated, currentUser, logout } = useAuth();
  const { navigateTo, showGlobalMessage } = useAppContext();

  const [activeTab, setActiveTab] = useState("ratings");
  const [ratings, setRatings] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchProfileData = useCallback(async () => {
    if (!isAuthenticated || !token) {
      setLoading(false);
      return;
    }
    setLoading(true);

    try {
      const [ratingsData, watchlistData, historyData] = await Promise.all([
        ApiService.getMyRatings(token, 0, 100).catch(() => []),
        ApiService.getMyWatchlist(token, 0, 50).catch(() => []),
        ApiService.getUserHistory(token, 0, 50).catch(() => []),
      ]);
      setRatings(ratingsData || []);
      setWatchlist(watchlistData || []);
      setHistory(historyData || []);
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, token]);

  useEffect(() => {
    fetchProfileData();
  }, [fetchProfileData]);

  if (!isAuthenticated) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center space-y-4">
        <h1 className="font-['Jost',sans-serif] text-2xl font-bold uppercase tracking-wider text-[#141414]">
          Your Profile
        </h1>
        <p className="text-sm text-[#5E5A52] leading-relaxed font-['Jost',sans-serif]">
          Log in to access your personal rating trajectory, watchlist entries, and sequential recommendation history.
        </p>
        <div className="pt-2">
          <button
            type="button"
            onClick={() => navigateTo("login")}
            className="px-6 py-3 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
          >
            Sign in to Your Account
          </button>
        </div>
      </div>
    );
  }

  const memberSince = currentUser?.created_at
    ? new Date(currentUser.created_at).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "Member";

  const handleCardClick = (movieId) => {
    navigateTo("movieDetail", movieId);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 space-y-10 text-left">
      {/* Profile Header Box */}
      <div className="p-6 sm:p-8 bg-white border border-[#D9D3C7] flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="flex items-center gap-4 sm:gap-5">
          <div className="w-14 h-14 rounded-full bg-[#141414] text-white flex items-center justify-center font-['Jost',sans-serif] font-bold text-xl uppercase">
            {currentUser?.email ? currentUser.email.substring(0, 2).toUpperCase() : "US"}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-['Jost',sans-serif] font-bold text-xl sm:text-2xl text-[#141414]">
                {currentUser?.email}
              </h1>
              {currentUser?.is_admin && (
                <span className="px-2 py-0.5 text-[10px] font-['Jost',sans-serif] font-bold uppercase tracking-wider bg-[#C8412B] text-white">
                  Admin
                </span>
              )}
            </div>
            <p className="text-xs text-[#5E5A52] font-medium mt-1">
              Member since {memberSince}
            </p>
          </div>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-4 sm:gap-6 self-start md:self-auto font-['Jost',sans-serif]">
          <div className="px-5 py-3 bg-[#FAF7F2] border border-[#D9D3C7] text-center min-w-[90px]">
            <span className="block text-xl font-bold text-[#141414] tabular-nums">
              {ratings.length}
            </span>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#5E5A52]">
              Ratings
            </span>
          </div>

          <div className="px-5 py-3 bg-[#FAF7F2] border border-[#D9D3C7] text-center min-w-[90px]">
            <span className="block text-xl font-bold text-[#141414] tabular-nums">
              {watchlist.length}
            </span>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#5E5A52]">
              Watchlist
            </span>
          </div>

          <button
            type="button"
            onClick={() => {
              logout();
              navigateTo("login");
              showGlobalMessage("Logged out successfully.", "success");
            }}
            className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-[#C8412B] hover:underline transition-colors cursor-pointer"
          >
            Sign Out
          </button>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex items-center gap-2 border-b border-[#D9D3C7] pb-3 font-['Jost',sans-serif]">
        <button
          type="button"
          onClick={() => setActiveTab("ratings")}
          className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer border ${
            activeTab === "ratings"
              ? "bg-[#141414] text-white border-[#141414]"
              : "bg-white text-[#5E5A52] border-[#D9D3C7] hover:border-[#141414]"
          }`}
        >
          Rated Titles ({ratings.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("watchlist")}
          className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer border ${
            activeTab === "watchlist"
              ? "bg-[#141414] text-white border-[#141414]"
              : "bg-white text-[#5E5A52] border-[#D9D3C7] hover:border-[#141414]"
          }`}
        >
          Watchlist ({watchlist.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("history")}
          className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer border ${
            activeTab === "history"
              ? "bg-[#141414] text-white border-[#141414]"
              : "bg-white text-[#5E5A52] border-[#D9D3C7] hover:border-[#141414]"
          }`}
        >
          Activity Log ({history.length})
        </button>
      </div>

      {loading ? (
        <LoadingSpinner text="Retrieving profile data..." />
      ) : (
        <>
          {/* TAB 1: RATED MOVIES */}
          {activeTab === "ratings" && (
            <div className="space-y-4">
              {ratings.length === 0 ? (
                <div className="p-10 border border-[#D9D3C7] bg-white text-center text-[#5E5A52] text-sm font-['Jost',sans-serif]">
                  You have not submitted any ratings yet. Rate movies in the catalogue to build your sequential model trajectory.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {ratings.map((r) => {
                    const ratingDate = r.timestamp
                      ? new Date(r.timestamp * 1000).toLocaleDateString("en-US", {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                        })
                      : "Recent";
                    return (
                      <div
                        key={r.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => handleCardClick(r.movie_id)}
                        className="p-4 bg-white border border-[#D9D3C7] hover:border-[#141414] transition-colors flex items-center justify-between gap-4 cursor-pointer"
                      >
                        <div>
                          <h3 className="font-['Jost',sans-serif] font-bold text-sm text-[#141414] line-clamp-1 uppercase tracking-wide">
                            {r.movie?.title || `Movie #${r.movie_id}`}
                          </h3>
                          <span className="text-xs text-[#5E5A52] font-medium">{ratingDate}</span>
                        </div>
                        <div className="flex-shrink-0">
                          <RatingStars rating={r.rating} size="sm" showNumeric={true} theme="ink" />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: WATCHLIST SUMMARY */}
          {activeTab === "watchlist" && (
            <div className="space-y-4">
              {watchlist.length === 0 ? (
                <div className="p-10 border border-[#D9D3C7] bg-white text-center text-[#5E5A52] text-sm font-['Jost',sans-serif]">
                  Your watchlist is currently empty.
                </div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 sm:gap-6">
                  {watchlist.map((item) =>
                    item.movie ? (
                      <MovieCard
                        key={item.id}
                        movie={item.movie}
                        onCardClick={handleCardClick}
                        isAuthenticated={true}
                      />
                    ) : null,
                  )}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: ACTIVITY LOG */}
          {activeTab === "history" && (
            <div className="space-y-3">
              {history.length === 0 ? (
                <div className="p-10 border border-[#D9D3C7] bg-white text-center text-[#5E5A52] text-sm font-['Jost',sans-serif]">
                  No logged telemetry interactions recorded.
                </div>
              ) : (
                <div className="space-y-2">
                  {history.map((h, idx) => {
                    const eventDate = h.timestamp
                      ? new Date(h.timestamp).toLocaleString("en-US", {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "Recently";

                    return (
                      <div
                        key={idx}
                        className="p-3.5 bg-white border border-[#D9D3C7] flex items-center justify-between text-xs sm:text-sm font-['Jost',sans-serif]"
                      >
                        <div className="flex items-center gap-3">
                          <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-[#141414] text-white">
                            {h.event_type}
                          </span>
                          <span
                            onClick={() => handleCardClick(h.movie_id)}
                            className="font-bold text-[#141414] hover:text-[#C8412B] cursor-pointer line-clamp-1 uppercase tracking-wide"
                          >
                            {h.movie_title || `Movie #${h.movie_id}`}
                          </span>
                        </div>
                        <span className="text-xs text-[#5E5A52] font-medium flex-shrink-0">
                          {eventDate}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default ProfilePage;
