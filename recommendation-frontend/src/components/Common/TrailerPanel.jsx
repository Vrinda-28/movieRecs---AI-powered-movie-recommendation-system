import React, { useState, useEffect } from "react";
import { Play } from "lucide-react";
import { backdropUrl } from "../../services/movieMedia";
import { parseMovieTitle } from "../../utils/movieTitle";

/**
 * Editorial TrailerPanel: Click-to-load YouTube embed with strict movie-specific trailer keys.
 * Never uses resource_url or fallback default videos.
 */
const TrailerPanel = ({ movie, media }) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [thumbError, setThumbError] = useState(false);

  // Reset playback state whenever movie ID changes
  const movieId = movie?.id || movie?.movie_id;
  useEffect(() => {
    setIsPlaying(false);
    setThumbError(false);
  }, [movieId]);

  const { title: cleanTitle, year } = parseMovieTitle(movie?.title || "");
  const trailer = media?.trailer;
  const videoKey = trailer?.key;

  // Validate YouTube video key
  const isValidKey = Boolean(videoKey && /^[A-Za-z0-9_-]{11}$/.test(videoKey));

  if (!isValidKey) {
    return (
      <div className="border border-[#D9D3C7] bg-[#FAF7F2] p-8 text-center space-y-3" id="trailer-section">
        <h4 className="font-['Jost',sans-serif] font-bold text-xs uppercase tracking-widest text-[#5E5A52]">
          TRAILER
        </h4>
        <p className="font-['Jost',sans-serif] text-sm text-[#141414] font-medium">
          Trailer unavailable for this title
        </p>
        <div className="pt-1">
          <a
            href={`https://www.youtube.com/results?search_query=${encodeURIComponent(cleanTitle + (year ? ` ${year}` : "") + " official trailer")}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
          >
            <Play className="w-3 h-3 fill-white" />
            <span>Search Trailer on YouTube</span>
          </a>
        </div>
      </div>
    );
  }

  const thumbUrl = !thumbError
    ? `https://i.ytimg.com/vi/${videoKey}/hqdefault.jpg`
    : backdropUrl(media, 780);

  return (
    <div className="space-y-2" id="trailer-section">
      <div className="flex items-center justify-between border-b border-[#D9D3C7] pb-1.5">
        <h3 className="font-['Jost',sans-serif] font-bold text-xs uppercase tracking-widest text-[#141414]">
          TRAILER — {cleanTitle}
        </h3>
        {trailer.name && (
          <span className="text-[11px] text-[#5E5A52] truncate max-w-[50%] font-medium">
            {trailer.name}
          </span>
        )}
      </div>

      <div className="relative w-full aspect-video bg-[#141414] overflow-hidden border border-[#D9D3C7]">
        {isPlaying ? (
          <iframe
            src={`https://www.youtube-nocookie.com/embed/${videoKey}?autoplay=1&rel=0`}
            title={`Official Trailer for ${cleanTitle}`}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            loading="lazy"
            className="w-full h-full border-0"
          />
        ) : (
          <div
            role="button"
            tabIndex={0}
            onClick={() => setIsPlaying(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setIsPlaying(true);
              }
            }}
            aria-label={`Play trailer: ${trailer.name || cleanTitle}`}
            className="group relative w-full h-full cursor-pointer flex items-center justify-center select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
          >
            {thumbUrl && (
              <img
                src={thumbUrl}
                alt={`Trailer still for ${cleanTitle}`}
                onError={() => setThumbError(true)}
                className="absolute inset-0 w-full h-full object-cover transition-transform duration-300 group-hover:scale-105 opacity-85"
              />
            )}

            {/* Dark scrim */}
            <div className="absolute inset-0 bg-black/30 group-hover:bg-black/20 transition-colors" />

            {/* Centered Circular Coral Play Button */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10 w-16 h-16 rounded-full bg-[#C8412B] group-hover:bg-[#A8321F] text-white flex items-center justify-center shadow-lg transition-transform group-hover:scale-110">
              <Play className="w-7 h-7 fill-white translate-x-0.5" />
            </div>

            {/* Bottom Caption Overlay */}
            {trailer.name && (
              <div className="absolute bottom-0 inset-x-0 p-3 bg-gradient-to-t from-black/80 to-transparent">
                <p className="text-xs text-white font-medium truncate font-['Jost',sans-serif]">
                  {trailer.name}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default TrailerPanel;
