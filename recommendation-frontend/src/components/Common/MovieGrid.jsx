import React from "react";
import MovieCard from "./MovieCard";

/**
 * Editorial MovieGrid:
 * - Responsive columns: 2 (mobile), 3-4 (tablet), 5-6 (desktop)
 * - Warm paper skeletons and designed empty states
 */
const MovieGrid = ({
  movies = [],
  loading = false,
  error = "",
  onCardClick,
  onRateMovieClick,
  isAuthenticated = false,
  skeletonCount = 12,
  showRank = false,
  emptyAction = null,
  className = "",
}) => {
  if (loading && movies.length === 0) {
    return (
      <div
        className={`grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 sm:gap-6 ${className}`}
        aria-label="Loading catalogue titles"
      >
        {Array.from({ length: skeletonCount }).map((_, idx) => (
          <div
            key={idx}
            className="flex flex-col bg-white border border-[#D9D3C7] animate-pulse overflow-hidden"
          >
            <div className="w-full aspect-[2/3] bg-[#EFEAE1]" />
            <div className="p-3.5 space-y-2 border-t border-[#D9D3C7]">
              <div className="h-4 bg-[#EFEAE1] w-4/5" />
              <div className="h-3 bg-[#EFEAE1] w-1/2" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error && movies.length === 0) {
    return (
      <div className="border border-[#D9D3C7] bg-white p-8 text-center my-6">
        <p className="font-['Jost',sans-serif] text-sm text-[#C8412B] font-semibold">{error}</p>
      </div>
    );
  }

  if (!loading && movies.length === 0) {
    return (
      <div className="border border-[#D9D3C7] bg-white p-12 text-center my-6">
        <h3 className="font-['Jost',sans-serif] font-bold text-base uppercase tracking-wider text-[#141414] mb-2">
          No Titles Found
        </h3>
        <p className="text-sm text-[#5E5A52] max-w-md mx-auto mb-4 font-['Jost',sans-serif]">
          We couldn't find any movies matching your current filters.
        </p>
        {emptyAction}
      </div>
    );
  }

  return (
    <div
      className={`grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 sm:gap-6 ${className}`}
    >
      {movies.map((movie, idx) => (
        <MovieCard
          key={`${movie.id || movie.movie_id}-${idx}`}
          movie={movie}
          rank={showRank ? idx + 1 : null}
          onCardClick={onCardClick}
          onRateMovieClick={onRateMovieClick}
          isAuthenticated={isAuthenticated}
          priority={idx < 4}
        />
      ))}
    </div>
  );
};

export default MovieGrid;
