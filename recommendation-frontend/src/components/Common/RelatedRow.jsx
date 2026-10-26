import React, { useRef, useState, useEffect } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import PosterImage from "./PosterImage";
import RatingStars from "./RatingStars";
import { parseMovieTitle } from "../../utils/movieTitle";

/**
 * Editorial Coral Related Movies Band.
 * Full-width coral strip with accessible outlined navigation arrows,
 * horizontal scroll-snap poster carousel, white typography and honest labeling.
 */
const RelatedRow = ({ movies = [], genre = "", currentMovieId, onMovieClick }) => {
  const scrollRef = useRef(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(true);

  // Filter out the current movie and take up to 12 titles
  const validMovies = movies
    .filter((m) => (m.id || m.movie_id) !== currentMovieId)
    .slice(0, 12);

  const checkScroll = () => {
    if (!scrollRef.current) return;
    const { scrollLeft, scrollWidth, clientWidth } = scrollRef.current;
    setCanScrollLeft(scrollLeft > 10);
    setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 10);
  };

  useEffect(() => {
    checkScroll();
  }, [validMovies]);

  const handleScroll = (direction) => {
    if (!scrollRef.current) return;
    const scrollAmount = scrollRef.current.clientWidth * 0.75;
    scrollRef.current.scrollBy({
      left: direction === "left" ? -scrollAmount : scrollAmount,
      behavior: "smooth",
    });
    setTimeout(checkScroll, 300);
  };

  if (validMovies.length < 4) {
    return null; // Omit band if fewer than 4 results
  }

  return (
    <section className="w-full bg-[#C8412B] text-white py-12 px-4 sm:px-6 md:px-8 my-12" aria-label={`More titles in ${genre}`}>
      <div className="max-w-6xl mx-auto">
        {/* Header flanked by hairline rules */}
        <div className="flex items-center gap-4 mb-2">
          <div className="flex-1 h-px bg-white/30" />
          <h2 className="font-['Jost',sans-serif] font-bold text-base sm:text-lg uppercase tracking-[0.14em] text-white text-center">
            MORE IN {genre || "THIS GENRE"}
          </h2>
          <div className="flex-1 h-px bg-white/30" />
        </div>

        <p className="text-center text-xs uppercase tracking-wider text-white/80 font-medium mb-8">
          Most-rated titles in the same genre
        </p>

        {/* Carousel Container */}
        <div className="relative group">
          {/* Scroll Left Button */}
          <button
            type="button"
            onClick={() => handleScroll("left")}
            disabled={!canScrollLeft}
            aria-label="Scroll left"
            className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-3 sm:-translate-x-5 z-20 w-10 h-10 rounded-full border border-white/60 bg-[#C8412B] hover:bg-[#A8321F] text-white flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>

          {/* Horizontally scrollable row with scroll-snap */}
          <div
            ref={scrollRef}
            onScroll={checkScroll}
            className="flex gap-4 sm:gap-6 overflow-x-auto no-scrollbar scroll-smooth snap-x snap-mandatory py-2 px-1"
          >
            {validMovies.map((movie) => {
              const movieId = movie.id || movie.movie_id;
              const { title: cleanTitle, year } = parseMovieTitle(movie.title);

              return (
                <div
                  key={movieId}
                  role="button"
                  tabIndex={0}
                  onClick={() => onMovieClick && onMovieClick(movieId)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onMovieClick && onMovieClick(movieId);
                    }
                  }}
                  className="flex-shrink-0 w-36 sm:w-44 snap-start group/item cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white p-1"
                >
                  <div className="aspect-[2/3] w-full overflow-hidden border border-white/30 bg-[#141414] shadow-md group-hover/item:border-white transition-colors">
                    <PosterImage
                      movie={movie}
                      title={movie.title}
                      genres={movie.genres}
                      targetWidth={185}
                      className="w-full h-full"
                    />
                  </div>

                  {/* Rating Stars (White) */}
                  <div className="mt-2.5">
                    <RatingStars
                      rating={movie.average_rating}
                      size="xs"
                      theme="white"
                      showNumeric={false}
                    />
                  </div>

                  {/* Title & Year */}
                  <h3
                    className="font-['Jost',sans-serif] font-bold text-xs uppercase tracking-wider text-white mt-1 line-clamp-1 group-hover/item:underline"
                    title={cleanTitle}
                  >
                    {cleanTitle}
                  </h3>
                  {year && (
                    <span className="text-[11px] text-white/80 font-medium">
                      ({year})
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Scroll Right Button */}
          <button
            type="button"
            onClick={() => handleScroll("right")}
            disabled={!canScrollRight}
            aria-label="Scroll right"
            className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-3 sm:translate-x-5 z-20 w-10 h-10 rounded-full border border-white/60 bg-[#C8412B] hover:bg-[#A8321F] text-white flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>
      </div>
    </section>
  );
};

export default RelatedRow;
