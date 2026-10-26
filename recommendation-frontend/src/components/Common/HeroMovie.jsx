import React from "react";
import PosterImage from "./PosterImage";
import RatingStars from "./RatingStars";
import WatchlistButton from "./WatchlistButton";
import { parseMovieTitle, parseGenres } from "../../utils/movieTitle";
import { useMovieMedia, backdropUrl } from "../../services/movieMedia";
import { ArrowRight, Star } from "lucide-react";

/**
 * Editorial HeroMovie:
 * - Full-bleed cinematic backdrop or flat ink panel if no backdrop is available
 * - Real synopsis excerpt from TMDB manifest, or factual catalogue line if missing
 * - Deterministic featured presentation
 * - Actions: View details, Rate, Watchlist
 */
const HeroMovie = ({
  movie,
  onViewDetails,
  onRateMovie,
  isAuthenticated = false,
  className = "",
}) => {
  const media = useMovieMedia(movie);

  if (!movie) return null;

  const movieId = movie.id || movie.movie_id;
  const { title: cleanTitle, year } = parseMovieTitle(movie.title);
  const genres = parseGenres(movie.genres);
  const backdrop = backdropUrl(media, 1280);

  // Real synopsis or strictly factual catalogue line
  const synopsis = media?.overview
    ? media.overview
    : `${genres.join(" · ")}${year ? ` · ${year}` : ""} · Rated by ${(movie.num_ratings || 0).toLocaleString()} members`;

  return (
    <section
      className={`relative w-full bg-[#141414] text-[#FAF7F2] overflow-hidden border-b border-[#D9D3C7] ${className}`}
      aria-label={`Featured presentation: ${cleanTitle}`}
    >
      {/* Full-bleed real backdrop image if present */}
      {backdrop && (
        <div className="absolute inset-0 z-0">
          <img
            src={backdrop}
            alt=""
            fetchPriority="high"
            className="w-full h-full object-cover object-top opacity-35"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#141414] via-[#141414]/75 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-r from-[#141414] via-[#141414]/80 to-transparent" />
        </div>
      )}

      {/* Hero Content Container */}
      <div className="relative z-10 max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-14 sm:py-20 md:py-24">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-8 md:gap-12">
          {/* Left Text Column */}
          <div className="flex-1 max-w-2xl space-y-4">
            {/* Editorial Label & Year */}
            <div className="flex items-center gap-3">
              <span className="font-['Jost',sans-serif] font-bold text-xs uppercase tracking-[0.16em] text-[#C8412B]">
                FEATURED DISCOVERY
              </span>
              {year && (
                <>
                  <span className="text-[#D9D3C7]/40 text-xs font-mono">/</span>
                  <span className="font-['Jost',sans-serif] text-xs font-semibold tracking-wider text-[#FAF7F2]/80">
                    {year}
                  </span>
                </>
              )}
            </div>

            {/* Main Title (tracked caps) */}
            <h1 className="font-['Jost',sans-serif] font-black text-3xl sm:text-4xl md:text-5xl uppercase tracking-[0.08em] leading-tight text-white">
              {cleanTitle}
            </h1>

            {/* Genres Separated by thin pipes */}
            <div className="flex flex-wrap items-center gap-2 text-xs font-['Jost',sans-serif] font-semibold uppercase tracking-wider text-[#FAF7F2]/80">
              {genres.map((g, idx) => (
                <React.Fragment key={g}>
                  {idx > 0 && <span className="text-white/30">|</span>}
                  <span>{g}</span>
                </React.Fragment>
              ))}
            </div>

            {/* Star Row & Community Count */}
            <div className="pt-1">
              <RatingStars
                rating={movie.average_rating}
                numRatings={movie.num_ratings}
                size="md"
                theme="white"
              />
            </div>

            {/* Real Synopsis or Factual Line */}
            <p className="text-sm sm:text-[15px] leading-relaxed text-[#FAF7F2]/90 line-clamp-3 pt-1 font-['Jost',sans-serif]">
              {synopsis}
            </p>

            {/* Actions: View Details, Rate, Watchlist */}
            <div className="flex flex-wrap items-center gap-3 pt-4">
              <button
                type="button"
                onClick={() => onViewDetails && onViewDetails(movieId)}
                className="px-6 py-3 bg-[#C8412B] hover:bg-[#A8321F] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors flex items-center gap-2 shadow-sm cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
              >
                <span>View Details</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>

              {isAuthenticated && onRateMovie && (
                <button
                  type="button"
                  onClick={() => onRateMovie(movie)}
                  className="px-5 py-3 bg-white/10 hover:bg-white/20 text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest border border-white/30 transition-colors flex items-center gap-1.5 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
                >
                  <Star className="w-3.5 h-3.5 fill-white/80" />
                  <span>Rate</span>
                </button>
              )}

              {isAuthenticated && (
                <WatchlistButton
                  movieId={movieId}
                  size="md"
                  className="!rounded-none !bg-white/10 hover:!bg-white/20 !border !border-white/30 !text-white"
                />
              )}
            </div>
          </div>

          {/* Right Poster Column */}
          <div className="w-44 sm:w-56 md:w-64 flex-shrink-0 self-center md:self-auto">
            <div className="aspect-[2/3] w-full border border-white/20 shadow-2xl bg-[#141414] overflow-hidden">
              <PosterImage
                movie={movie}
                title={movie.title}
                genres={movie.genres}
                priority={true}
                targetWidth={500}
                className="w-full h-full"
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default HeroMovie;
