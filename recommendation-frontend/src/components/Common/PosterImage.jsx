import React, { useState, useEffect } from "react";
import { parseMovieTitle, parseGenres } from "../../utils/movieTitle";
import { useMovieMedia, posterUrl } from "../../services/movieMedia";

/**
 * Editorial cinema fallback card when no poster is available.
 * Displays the full movie title, year, first genre, and an honest archival note.
 * Never displays monogram/initials placeholders.
 */
export const PosterFallback = ({
  movie,
  title = "Untitled",
  genres = "",
  className = "",
  aspectRatio = "aspect-[2/3]",
}) => {
  const parsed = parseMovieTitle(movie?.title || title);
  const genreList = parseGenres(movie?.genres || genres);
  const firstGenre = genreList[0] || null;

  return (
    <div
      className={`relative w-full ${aspectRatio} bg-gradient-to-b from-[#1C1A18] via-[#141312] to-[#0D0C0B] border border-[#2E2A24] p-3.5 flex flex-col justify-between text-[#FAF7F2] select-none transition-colors overflow-hidden ${className}`}
      aria-label={`Poster not available for ${parsed.title}`}
    >
      {/* Decorative subtle film perforations along top edge */}
      <div className="absolute top-0 left-0 right-0 h-1.5 flex justify-between px-1 opacity-25 overflow-hidden pointer-events-none">
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="w-1.5 h-1 bg-[#4A433A] rounded-xs" />
        ))}
      </div>

      {/* Top Header: Year & Genre Badge */}
      <div className="pt-1 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-[#A69F92]">
        <span className="font-['Jost',sans-serif] px-1.5 py-0.5 bg-[#24211D] rounded-xs border border-[#3D362D]">
          {parsed.year || "Catalogue"}
        </span>
        {firstGenre && (
          <span className="truncate max-w-[55%] font-['Jost',sans-serif] px-1.5 py-0.5 bg-[#24211D] rounded-xs border border-[#3D362D] text-[#C8412B]">
            {firstGenre}
          </span>
        )}
      </div>

      {/* Centerpiece: Subtle cinema camera emblem & Title */}
      <div className="my-auto py-2 text-center relative z-10 flex flex-col items-center">
        <div className="w-8 h-8 rounded-full border border-[#3D362D] bg-[#24211D] flex items-center justify-center mb-2 text-[#C8412B] shadow-sm">
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <rect width="18" height="13" x="3" y="8" rx="2" ry="2" />
            <polyline points="16 3 12 8 8 3" />
          </svg>
        </div>

        <h4 className="font-['Jost',sans-serif] font-bold text-sm sm:text-base leading-snug uppercase tracking-wide text-[#FAF7F2] line-clamp-3 px-1">
          {parsed.title}
        </h4>
        {parsed.altTitle && (
          <p className="text-xs text-[#A69F92] italic font-['Cormorant_Garamond',serif] mt-1 line-clamp-1">
            ({parsed.altTitle})
          </p>
        )}
      </div>

      {/* Bottom note: Calm and honest editorial disclaimer */}
      <div className="pt-2 border-t border-[#2E2A24] flex items-center justify-between text-[9px] uppercase tracking-widest text-[#8C8273] font-semibold">
        <span>Archival Record</span>
        <span className="text-[#6E6659]">Poster Pending</span>
      </div>

      {/* Decorative subtle film perforations along bottom edge */}
      <div className="absolute bottom-0 left-0 right-0 h-1.5 flex justify-between px-1 opacity-25 overflow-hidden pointer-events-none">
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="w-1.5 h-1 bg-[#4A433A] rounded-xs" />
        ))}
      </div>
    </div>
  );
};

/**
 * Reusable poster image with TMDB integration, safe image error fallback,
 * and zero layout shifts (fixed 2:3 aspect ratio).
 */
const PosterImage = ({
  movie,
  src,
  title,
  genres,
  alt,
  className = "",
  aspectRatio = "aspect-[2/3]",
  priority = false,
  targetWidth = 342,
}) => {
  const [imageError, setImageError] = useState(false);

  // Derive resolved source
  const media = useMovieMedia(movie);
  const resolvedSrc = src || posterUrl(media, targetWidth);

  // Reset image error state when movie or source changes
  useEffect(() => {
    setImageError(false);
  }, [resolvedSrc, movie?.id, movie?.movie_lens_id]);

  const movieTitle = movie?.title || title || "Movie";
  const parsed = parseMovieTitle(movieTitle);
  const altText = alt || `Poster for ${parsed.title}${parsed.year ? ` (${parsed.year})` : ""}`;

  // If no source or error occurred, render calm editorial fallback
  if (!resolvedSrc || imageError) {
    return (
      <PosterFallback
        movie={movie}
        title={movieTitle}
        genres={genres || movie?.genres}
        className={className}
        aspectRatio={aspectRatio}
      />
    );
  }

  return (
    <div className={`relative w-full ${aspectRatio} overflow-hidden bg-[#EFEAE1] border border-[#D9D3C7]/80 ${className}`}>
      <img
        src={resolvedSrc}
        alt={altText}
        width={targetWidth}
        height={Math.round((targetWidth * 3) / 2)}
        loading={priority ? "eager" : "lazy"}
        fetchPriority={priority ? "high" : "auto"}
        decoding="async"
        onError={() => setImageError(true)}
        className="w-full h-full object-cover transition-transform duration-200 ease-out group-hover:scale-105"
      />
    </div>
  );
};

export default PosterImage;
