import React from "react";
import PosterImage from "./PosterImage";
import RatingStars from "./RatingStars";
import { parseMovieTitle, parseGenres } from "../../utils/movieTitle";

/**
 * Editorial MovieCard: 2:3 portrait poster, truthful badges, clean typography,
 * hairline borders, and strict avoidance of placeholder resource_url.
 */
const MovieCard = ({
  movie,
  rank = null,
  onCardClick,
  priority = false,
  className = "",
}) => {
  if (!movie) return null;

  const movieId = movie.id || movie.movie_id;
  const { title: cleanTitle, year } = parseMovieTitle(movie.title);
  const genres = parseGenres(movie.genres);
  const firstTwoGenres = genres.slice(0, 2).join(" · ");

  const handleKeyDown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onCardClick && onCardClick(movieId);
    }
  };

  const isPersonalized = movie.is_personalized === true;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onCardClick && onCardClick(movieId)}
      onKeyDown={handleKeyDown}
      aria-label={`View details for ${cleanTitle}${year ? ` (${year})` : ""}`}
      className={`group relative flex flex-col bg-white border border-[#D9D3C7] transition-all duration-200 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B] focus-visible:ring-offset-2 hover:-translate-y-1 hover:shadow-md ${className}`}
    >
      {/* Poster with 2:3 aspect ratio */}
      <div className="relative w-full aspect-[2/3] overflow-hidden bg-[#EFEAE1]">
        <PosterImage
          movie={movie}
          title={movie.title}
          genres={movie.genres}
          priority={priority}
          targetWidth={342}
          className="w-full h-full"
        />

        {/* Optional rank numeral (1..N) */}
        {rank !== null && rank !== undefined && (
          <div className="absolute top-2 left-2 z-10 w-7 h-7 bg-[#141414] text-white font-['Jost',sans-serif] font-bold text-xs flex items-center justify-center shadow">
            {rank}
          </div>
        )}

        {/* Personalized / Popularity Badge */}
        {movie.is_personalized !== undefined && (
          <div className="absolute top-2 right-2 z-10">
            {isPersonalized ? (
              <span className="inline-block px-2 py-0.5 text-[10px] font-['Jost',sans-serif] font-bold uppercase tracking-wider bg-[#C8412B] text-white shadow-sm">
                For you
              </span>
            ) : (
              <span className="inline-block px-2 py-0.5 text-[10px] font-['Jost',sans-serif] font-semibold uppercase tracking-wider bg-[#141414]/80 text-[#FAF7F2] backdrop-blur-xs">
                Popular pick
              </span>
            )}
          </div>
        )}
      </div>

      {/* Editorial Content Below Poster */}
      <div className="p-3.5 flex flex-col flex-grow justify-between gap-2.5 bg-white border-t border-[#D9D3C7]">
        <div>
          {/* Title in readable geometric sans */}
          <h3
            className="font-['Jost',sans-serif] font-bold text-sm sm:text-[15px] text-[#141414] group-hover:text-[#C8412B] group-hover:underline line-clamp-2 leading-snug tracking-wide uppercase transition-colors"
            title={cleanTitle}
          >
            {cleanTitle}
          </h3>

          {/* Year and Genres */}
          <p className="text-[12px] text-[#5E5A52] font-medium mt-1 truncate">
            {year ? `${year}` : ""}
            {year && firstTwoGenres ? "  ·  " : ""}
            {firstTwoGenres}
          </p>

          {/* Truthful Recommendation Reason (if provided by API) */}
          {movie.reason_text && (
            <p className="text-[11px] text-[#5E5A52] italic font-['Cormorant_Garamond',serif] mt-1.5 line-clamp-2 border-l-2 border-[#C8412B] pl-1.5">
              {movie.reason_text}
            </p>
          )}
        </div>

        {/* Community Rating stars & count */}
        <div className="pt-2 border-t border-[#D9D3C7]/60 flex items-center justify-between">
          <RatingStars
            rating={movie.average_rating}
            numRatings={movie.num_ratings}
            size="xs"
            theme="ink"
          />

          {movie.user_rating && (
            <span
              className="text-[11px] font-bold text-[#C8412B] tabular-nums"
              title={`Your rating: ${movie.user_rating}/5`}
            >
              ★ {movie.user_rating}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default MovieCard;
