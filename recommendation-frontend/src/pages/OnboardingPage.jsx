import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useAppContext } from "../contexts/AppContext";
import ApiService from "../services/ApiService";
import PosterImage from "../components/Common/PosterImage";
import LoadingSpinner from "../components/Common/LoadingSpinner";
import { parseMovieTitle, parseGenres } from "../utils/movieTitle";

const MIN_REQUIRED = 3;
const GOAL = 6;

// Star rating control
const StarControl = ({ value, onChange }) => {
  const [hover, setHover] = useState(0);
  const display = hover || value || 0;

  return (
    <div role="group" aria-label="Rate this movie" className="flex gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          aria-label={`Rate ${star} star${star > 1 ? "s" : ""}`}
          onClick={() => onChange(star)}
          onMouseEnter={() => setHover(star)}
          onMouseLeave={() => setHover(0)}
          className={`text-lg transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C8412B] ${
            star <= display ? "text-[#C8412B]" : "text-[#D9D3C7] hover:text-[#5E5A52]"
          }`}
        >
          ★
        </button>
      ))}
    </div>
  );
};

// Onboarding movie card
const OnboardingCard = ({ movie, onRate, submitting }) => {
  const [rating, setRating] = useState(0);
  const [submitted, setSubmitted] = useState(false);
  const { title, year } = parseMovieTitle(movie.title || "");
  const genres = parseGenres(movie.genres);

  const handleSubmit = async () => {
    if (rating === 0 || submitting) return;
    const ok = await onRate(movie.id, rating);
    if (ok) setSubmitted(true);
  };

  return (
    <div
      className={`relative flex flex-col bg-white border transition-all duration-200 ${
        submitted
          ? "border-[#C8412B] shadow-sm"
          : "border-[#D9D3C7] hover:border-[#141414]"
      }`}
    >
      {/* Submitted overlay */}
      {submitted && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-[#FAF7F2]/90 backdrop-blur-xs p-4">
          <div className="text-center space-y-1">
            <div className="text-2xl text-[#C8412B]">✓</div>
            <p className="text-xs font-bold font-['Jost',sans-serif] uppercase tracking-wider text-[#141414]">
              Rated {rating} ★
            </p>
          </div>
        </div>
      )}

      {/* Poster with 2:3 ratio */}
      <div className="aspect-[2/3] overflow-hidden bg-[#EFEAE1]">
        <PosterImage
          movie={movie}
          title={movie.title}
          genres={movie.genres}
          targetWidth={185}
          className="w-full h-full"
        />
      </div>

      {/* Details & Rating */}
      <div className="p-3 flex flex-col gap-2 flex-1 justify-between bg-white border-t border-[#D9D3C7]">
        <div>
          <h3
            className="font-['Jost',sans-serif] font-bold text-xs uppercase tracking-wide text-[#141414] line-clamp-2 leading-tight"
            title={title}
          >
            {title}
          </h3>
          {year && <p className="text-[11px] text-[#5E5A52] font-medium mt-0.5">{year}</p>}

          {genres.length > 0 && (
            <p className="text-[10px] text-[#5E5A52] uppercase tracking-wider font-semibold truncate mt-1">
              {genres[0]}
            </p>
          )}
        </div>

        <div className="pt-2 border-t border-[#D9D3C7]/60 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#5E5A52]">
              Rating
            </span>
            <StarControl value={rating} onChange={setRating} />
          </div>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={rating === 0 || submitted}
            className={`w-full py-1.5 text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer ${
              rating === 0 || submitted
                ? "bg-[#EFEAE1] text-[#5E5A52] cursor-not-allowed"
                : "bg-[#141414] hover:bg-[#C8412B] text-white"
            }`}
          >
            {submitted ? "Done ✓" : rating > 0 ? "Submit" : "Select ★"}
          </button>
        </div>
      </div>
    </div>
  );
};

// Progress bar
const ProgressBar = ({ count, goal = GOAL, min = MIN_REQUIRED }) => {
  const pct = Math.min(100, (count / goal) * 100);
  const reachedMin = count >= min;
  const reachedGoal = count >= goal;

  return (
    <div className="space-y-2 p-5 bg-white border border-[#D9D3C7]">
      <div className="flex items-center justify-between text-xs font-['Jost',sans-serif]">
        <span className="text-[#5E5A52] uppercase tracking-wider font-semibold">
          <strong className="text-[#141414] text-sm">{count}</strong> / {goal} titles rated
        </span>
        <span
          className={`font-bold uppercase tracking-wider ${
            reachedGoal
              ? "text-[#C8412B]"
              : reachedMin
              ? "text-[#141414]"
              : "text-[#5E5A52]"
          }`}
        >
          {reachedGoal
            ? "Taste profile initialized!"
            : reachedMin
            ? "Personalization unlocked"
            : `${min - count} more to unlock personalization`}
        </span>
      </div>
      <div className="h-2 bg-[#EFEAE1] border border-[#D9D3C7]/80 overflow-hidden">
        <div
          className={`h-full transition-all duration-300 ${
            reachedMin ? "bg-[#C8412B]" : "bg-[#141414]"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
};

const OnboardingPage = () => {
  const { isAuthenticated, token } = useAuth();
  const { navigateTo, showGlobalMessage } = useAppContext();

  const [movies, setMovies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [ratedCount, setRatedCount] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isAuthenticated) {
      showGlobalMessage("Please log in to complete onboarding.", "error");
      navigateTo("login");
      return;
    }
    setLoading(true);
    ApiService.getOnboardingMovies(16)
      .then((data) => setMovies(data || []))
      .catch((err) => {
        setError(err.message || "Failed to load onboarding movies.");
      })
      .finally(() => setLoading(false));
  }, [isAuthenticated, navigateTo, showGlobalMessage]);

  const handleRate = useCallback(
    async (movieId, rating) => {
      if (!token) return false;
      setSubmitting(true);
      try {
        await ApiService.rateMovie(
          { movie_id: movieId, rating, timestamp: Math.floor(Date.now() / 1000) },
          token,
        );
        setRatedCount((c) => c + 1);
        return true;
      } catch (err) {
        showGlobalMessage(err.message || "Failed to save rating.", "error");
        return false;
      } finally {
        setSubmitting(false);
      }
    },
    [token, showGlobalMessage],
  );

  const handleFinish = () => {
    if (ratedCount === 0) {
      showGlobalMessage("Rate at least one movie before finishing.", "error");
      return;
    }
    showGlobalMessage(
      ratedCount >= MIN_REQUIRED
        ? "Taste profile ready! Loading your recommendations…"
        : `Saved ${ratedCount} rating${ratedCount > 1 ? "s" : ""}. Rate ${MIN_REQUIRED - ratedCount} more to unlock personalization.`,
      "success",
    );
    navigateTo("recommendations");
  };

  if (loading) return <LoadingSpinner text="Preparing onboarding selection…" />;

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 space-y-8">
      {/* Header */}
      <div className="space-y-2 border-b border-[#D9D3C7] pb-6">
        <h1 className="font-['Jost',sans-serif] font-bold text-2xl sm:text-3xl uppercase tracking-[0.1em] text-[#141414]">
          Build Your Taste Profile
        </h1>
        <p className="text-xs sm:text-sm text-[#5E5A52] leading-relaxed max-w-2xl font-['Jost',sans-serif]">
          Rate titles across diverse genres to train your chronological interaction sequence for the sequential recommendation model.
        </p>
      </div>

      {/* Progress */}
      <ProgressBar count={ratedCount} />

      {error && (
        <div className="p-4 border border-[#C8412B] bg-white text-xs font-semibold text-[#C8412B]">
          {error}
        </div>
      )}

      {/* Movie Grid */}
      {movies.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3 sm:gap-4">
          {movies.map((movie) => (
            <OnboardingCard
              key={movie.id}
              movie={movie}
              onRate={handleRate}
              submitting={submitting}
            />
          ))}
        </div>
      )}

      {/* Bottom Action Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-6 border-t border-[#D9D3C7]">
        <button
          type="button"
          onClick={() => navigateTo("home")}
          className="text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#5E5A52] hover:text-[#141414] cursor-pointer"
        >
          Skip for now
        </button>

        <button
          type="button"
          onClick={handleFinish}
          className="px-8 py-3 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
        >
          {ratedCount >= MIN_REQUIRED
            ? "View Recommendations →"
            : `Save & Continue (${ratedCount} Rated)`}
        </button>
      </div>
    </div>
  );
};

export default OnboardingPage;
