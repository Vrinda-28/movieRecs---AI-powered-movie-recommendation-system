import React, { useState, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { useAppContext } from "../../contexts/AppContext";
import ApiService from "../../services/ApiService";
import { Bookmark } from "lucide-react";

/**
 * Editorial WatchlistButton with optimistic updates and flat styling.
 */
const WatchlistButton = ({ movieId, className = "" }) => {
  const { isAuthenticated, token } = useAuth();
  const { navigateTo, showGlobalMessage } = useAppContext();

  const [inWatchlist, setInWatchlist] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let isMounted = true;
    if (isAuthenticated && token && movieId) {
      ApiService.checkWatchlist(movieId, token)
        .then((res) => {
          if (isMounted && res && typeof res.in_watchlist === "boolean") {
            setInWatchlist(res.in_watchlist);
          }
        })
        .catch(() => {});
    } else {
      setInWatchlist(false);
    }
    return () => {
      isMounted = false;
    };
  }, [movieId, isAuthenticated, token]);

  const handleToggle = async (e) => {
    e.stopPropagation();
    if (!isAuthenticated) {
      showGlobalMessage("Please log in to add movies to your watchlist.", "error");
      navigateTo("login");
      return;
    }

    const previousState = inWatchlist;
    setInWatchlist(!previousState);
    setLoading(true);

    try {
      if (previousState) {
        await ApiService.removeFromWatchlist(movieId, token);
        showGlobalMessage("Removed from your watchlist.", "success");
      } else {
        await ApiService.addToWatchlist(movieId, token);
        showGlobalMessage("Saved to your watchlist!", "success");
      }
    } catch (err) {
      setInWatchlist(previousState);
      showGlobalMessage(err.message || "Failed to update watchlist.", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleToggle}
      disabled={loading}
      aria-label={inWatchlist ? "Remove from watchlist" : "Add to watchlist"}
      className={`px-5 py-3 text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest border transition-colors flex items-center gap-2 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B] ${
        inWatchlist
          ? "bg-[#C8412B] text-white border-[#C8412B]"
          : "bg-white text-[#141414] border-[#D9D3C7] hover:border-[#141414]"
      } ${className}`}
    >
      <Bookmark
        className={`w-3.5 h-3.5 ${inWatchlist ? "fill-white" : ""}`}
      />
      <span>{inWatchlist ? "Saved" : "+ Watchlist"}</span>
    </button>
  );
};

export default WatchlistButton;
