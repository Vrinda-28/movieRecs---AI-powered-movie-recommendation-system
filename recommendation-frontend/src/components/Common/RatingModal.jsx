import React, { useState, useEffect } from "react";
import StarRatingInput from "./StarRatingInput";
import ApiService from "../../services/ApiService";
import { useAppContext } from "../../contexts/AppContext";
import { parseMovieTitle } from "../../utils/movieTitle";

const RatingModal = ({ movie, show, onClose, token }) => {
  const [currentRating, setCurrentRating] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const { showGlobalMessage } = useAppContext();

  useEffect(() => {
    if (show && movie) {
      setCurrentRating(movie.user_rating || 0);
      setErrorMsg("");
      setSubmitting(false);
    }
  }, [show, movie]);

  if (!show || !movie) return null;

  const { title: cleanTitle } = parseMovieTitle(movie.title);
  const movieId = movie.id || movie.movie_id;

  const handleRate = async () => {
    if (currentRating === 0) {
      setErrorMsg("Please select a rating between 1 and 5 stars.");
      return;
    }
    setErrorMsg("");
    setSubmitting(true);

    try {
      const ratingData = {
        movie_id: movieId,
        rating: currentRating,
        timestamp: Math.floor(Date.now() / 1000),
      };
      await ApiService.rateMovie(ratingData, token);
      showGlobalMessage(
        `Recorded ${currentRating}★ rating for "${cleanTitle}".`,
        "success",
      );
      onClose();
    } catch (error) {
      setErrorMsg(error.message || "Failed to submit rating.");
      setSubmitting(false);
    }
  };

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rating-modal-title"
    >
      <div className="modal-content text-left space-y-4">
        <div>
          <span className="text-[11px] font-['Jost',sans-serif] font-bold uppercase tracking-widest text-[#C8412B]">
            MEMBER RATING
          </span>
          <h3
            id="rating-modal-title"
            className="font-['Jost',sans-serif] font-bold text-xl uppercase tracking-wider text-[#141414] mt-1 line-clamp-1"
          >
            Rate "{cleanTitle}"
          </h3>
        </div>

        <div className="py-3">
          <StarRatingInput rating={currentRating} setRating={setCurrentRating} />
        </div>

        {errorMsg && (
          <p className="text-xs font-semibold text-[#C8412B] bg-[#FAF7F2] border border-[#C8412B]/40 p-2.5">
            {errorMsg}
          </p>
        )}

        <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#D9D3C7]">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 bg-transparent hover:bg-[#EFEAE1] text-[#141414] text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider border border-[#D9D3C7] transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleRate}
            disabled={submitting || currentRating === 0}
            className="px-6 py-2.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
          >
            {submitting ? "Saving..." : "Save Rating"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default RatingModal;
