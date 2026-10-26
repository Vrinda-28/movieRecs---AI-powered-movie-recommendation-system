import React, { useRef, useState, useEffect } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import MovieCard from "./MovieCard";

/**
 * Editorial SectionRow: Horizontal scrolling carousel with hairline headings,
 * rank badges, accessible arrows, and editorial tokens.
 */
const SectionRow = ({
  title,
  subtitle,
  badge,
  movies = [],
  loading = false,
  showRank = false,
  onCardClick,
  onRateMovieClick,
  isAuthenticated = false,
  emptyMessage = "No titles available right now.",
  className = "",
}) => {
  const rowRef = useRef(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(true);

  const checkScroll = () => {
    if (!rowRef.current) return;
    const { scrollLeft, scrollWidth, clientWidth } = rowRef.current;
    setCanScrollLeft(scrollLeft > 10);
    setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 10);
  };

  useEffect(() => {
    checkScroll();
  }, [movies]);

  const scroll = (direction) => {
    if (!rowRef.current) return;
    const amount = rowRef.current.clientWidth * 0.75;
    rowRef.current.scrollBy({
      left: direction === "left" ? -amount : amount,
      behavior: "smooth",
    });
    setTimeout(checkScroll, 300);
  };

  return (
    <section className={`mb-12 sm:mb-16 ${className}`} aria-label={title}>
      {/* Editorial Heading with hairline rule */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-4 pb-2 border-b border-[#D9D3C7]">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="font-['Jost',sans-serif] font-bold text-lg sm:text-xl uppercase tracking-[0.1em] text-[#141414]">
              {title}
            </h2>
            {badge && (
              <span className="px-2 py-0.5 text-[10px] font-['Jost',sans-serif] font-bold uppercase tracking-wider bg-[#141414] text-white">
                {badge}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="text-xs text-[#5E5A52] font-medium mt-1">
              {subtitle}
            </p>
          )}
        </div>

        {/* Scroll Nav Buttons */}
        {movies.length > 0 && !loading && (
          <div className="flex items-center gap-1.5 self-end sm:self-auto">
            <button
              type="button"
              onClick={() => scroll("left")}
              disabled={!canScrollLeft}
              aria-label={`Scroll ${title} left`}
              className="w-8 h-8 rounded-full border border-[#D9D3C7] bg-white hover:bg-[#EFEAE1] text-[#141414] flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => scroll("right")}
              disabled={!canScrollRight}
              aria-label={`Scroll ${title} right`}
              className="w-8 h-8 rounded-full border border-[#D9D3C7] bg-white hover:bg-[#EFEAE1] text-[#141414] flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* Loading Skeleton */}
      {loading && (
        <div className="flex gap-4 overflow-hidden py-2">
          {Array.from({ length: 5 }).map((_, idx) => (
            <div
              key={idx}
              className="w-40 sm:w-48 flex-shrink-0 bg-white border border-[#D9D3C7] animate-pulse overflow-hidden"
            >
              <div className="w-full aspect-[2/3] bg-[#EFEAE1]" />
              <div className="p-3 space-y-2 border-t border-[#D9D3C7]">
                <div className="h-3.5 bg-[#EFEAE1] w-3/4" />
                <div className="h-3 bg-[#EFEAE1] w-1/2" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && movies.length === 0 && (
        <div className="border border-[#D9D3C7] bg-white p-8 text-center text-xs font-['Jost',sans-serif] uppercase tracking-wider text-[#5E5A52]">
          {emptyMessage}
        </div>
      )}

      {/* Carousel Movies */}
      {!loading && movies.length > 0 && (
        <div
          ref={rowRef}
          onScroll={checkScroll}
          className="flex gap-4 sm:gap-5 overflow-x-auto py-2 scroll-smooth no-scrollbar focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
          tabIndex={0}
          aria-label={`${title} carousel`}
        >
          {movies.map((movie, idx) => (
            <div key={`${movie.id || movie.movie_id}-${idx}`} className="w-40 sm:w-48 flex-shrink-0">
              <MovieCard
                movie={movie}
                rank={showRank ? idx + 1 : null}
                onCardClick={onCardClick}
                onRateMovieClick={onRateMovieClick}
                isAuthenticated={isAuthenticated}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default SectionRow;
