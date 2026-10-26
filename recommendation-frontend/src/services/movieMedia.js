/**
 * Frontend media adapter: fetches static movie media manifest once per session
 * and provides safe helpers for posters, backdrops, and trailer data.
 */

import { useState, useEffect } from "react";
import staticManifest from "../../public/data/movieMedia.json" with { type: "json" };
import { parseMovieTitle, normalizeTitle } from "../utils/movieTitle.js";

let manifestPromise = null;
const listeners = new Set();
function notifyListeners() {
  listeners.forEach((fn) => {
    try {
      fn();
    } catch {
      // Ignore listener error
    }
  });
}

let cachedManifest = {
  meta: staticManifest?.meta || {
    imageBase: "https://image.tmdb.org/t/p/",
    posterSizes: ["w185", "w342", "w500", "original"],
    backdropSizes: ["w780", "w1280", "original"],
    source: "TMDB",
  },
  items: staticManifest?.items || {},
};

// Title-based index mapping normalized titles to media items
let titleIndex = null;

function buildTitleIndex(items) {
  const index = new Map();
  if (!items) return index;
  for (const [key, item] of Object.entries(items)) {
    if (!item) continue;
    if (item.matchedTitle) {
      const norm = normalizeTitle(item.matchedTitle);
      if (norm) {
        if (!index.has(norm)) {
          index.set(norm, []);
        }
        index.get(norm).push({ key, item });
      }
    }
  }
  return index;
}

/**
 * Checks whether a manifest media item actually belongs to the given movie.
 * Prevents displaying a poster or metadata from a completely different film.
 */
export function isMediaCompatible(movie, mediaItem) {
  if (!mediaItem || !movie) return false;
  if (!movie.title) return true;

  const parsedMovie = parseMovieTitle(movie.title);
  const movieYear = movie.year || parsedMovie.year;
  const mediaYear = mediaItem.matchedYear;

  // Strict release year check: if both years are known, reject remakes / different era films (>1 yr apart)
  if (movieYear && mediaYear && Math.abs(movieYear - mediaYear) > 1) {
    return false;
  }

  const normMovie = normalizeTitle(parsedMovie.title);
  const normMedia = normalizeTitle(mediaItem.matchedTitle || "");

  if (!normMovie || !normMedia) return false;

  const titlesToTest = [normMovie];
  if (parsedMovie.altTitle) {
    const normAlt = normalizeTitle(parsedMovie.altTitle);
    if (normAlt) titlesToTest.push(normAlt);
  }

  const strippedMedia = normMedia.replace(/\s+/g, "");

  for (const t of titlesToTest) {
    // Exact or space/punctuation stripped match
    if (t === normMedia || t.replace(/\s+/g, "") === strippedMedia) {
      return true;
    }
  }

  return false;
}

/**
 * Generates an elegant SVG data URI fallback poster.
 * Displays film title, year, and genre in an archival editorial aesthetic.
 */
export function getFallbackPosterDataUrl({ title = "Movie", year = null, genre = null } = {}) {
  const parsed = parseMovieTitle(title);
  const displayTitle = (parsed.title || "Cinema Archive").slice(0, 48);
  const displayYear = year || parsed.year || "Catalogue";
  const displayGenre = genre || "Feature Film";

  // Escape XML characters
  const escapeXml = (s) =>
    String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&apos;");

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 342 513" width="342" height="513">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#1A1816"/>
      <stop offset="50%" stop-color="#141312"/>
      <stop offset="100%" stop-color="#0D0C0B"/>
    </linearGradient>
    <pattern id="filmHoles" x="0" y="0" width="16" height="12" patternUnits="userSpaceOnUse">
      <rect x="3" y="2" width="10" height="8" rx="2" fill="#2E2A24"/>
    </pattern>
  </defs>
  <rect width="342" height="513" fill="url(#bg)"/>
  
  <!-- Film border perforations -->
  <rect x="0" y="0" width="342" height="12" fill="url(#filmHoles)"/>
  <rect x="0" y="501" width="342" height="12" fill="url(#filmHoles)"/>
  <rect x="16" y="24" width="310" height="465" fill="none" stroke="#2E2A24" stroke-width="1"/>

  <!-- Top Metadata Header -->
  <text x="32" y="56" fill="#8C8273" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="10" font-weight="700" letter-spacing="1.5" text-transform="uppercase">${escapeXml(displayYear)}</text>
  <text x="310" y="56" text-anchor="end" fill="#8C8273" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="10" font-weight="700" letter-spacing="1.5" text-transform="uppercase">${escapeXml(displayGenre)}</text>

  <!-- Cinema Icon Emblem -->
  <g transform="translate(171, 180)" stroke="#C8412B" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="0" cy="0" r="32" stroke="#3D362D"/>
    <circle cx="0" cy="0" r="8" fill="#C8412B" fill-opacity="0.3"/>
    <line x1="0" y1="-32" x2="0" y2="-8" stroke="#3D362D"/>
    <line x1="0" y1="8" x2="0" y2="32" stroke="#3D362D"/>
    <line x1="-32" y1="0" x2="-8" y2="0" stroke="#3D362D"/>
    <line x1="8" y1="0" x2="32" y2="0" stroke="#3D362D"/>
  </g>

  <!-- Title Centerpiece -->
  <text x="171" y="280" text-anchor="middle" fill="#FAF7F2" font-family="'Times New Roman', Times, serif" font-size="20" font-weight="600" letter-spacing="0.5">
    ${escapeXml(displayTitle)}
  </text>

  <!-- Footer Disclaimer -->
  <line x1="48" y1="440" x2="294" y2="440" stroke="#2E2A24" stroke-width="1"/>
  <text x="171" y="462" text-anchor="middle" fill="#5E5A52" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="9" font-weight="600" letter-spacing="2" text-transform="uppercase">
    ARCHIVAL RECORD • POSTER PENDING
  </text>
</svg>`;

  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/**
 * Loads the movie media manifest once per browser session.
 * Never throws; degrades gracefully to empty cache.
 */
export async function loadMediaManifest() {
  if (manifestPromise) return manifestPromise;

  manifestPromise = (async () => {
    try {
      const res = await fetch(`/data/movieMedia.json?t=${Date.now()}`, {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const data = await res.json();
        if (data && typeof data === "object") {
          cachedManifest = {
            meta: data.meta || cachedManifest.meta,
            items: { ...(cachedManifest.items || {}), ...(data.items || {}) },
          };
          titleIndex = buildTitleIndex(cachedManifest.items);
          notifyListeners();
        }
      }
    } catch (err) {
      console.warn("Failed to load /data/movieMedia.json, using fallback adapter:", err);
    }
    return cachedManifest;
  })();

  return manifestPromise;
}

// Kick off single session load immediately in background
if (typeof window !== "undefined") {
  loadMediaManifest().catch(() => {});
}

/**
 * Returns media entry for a given movie object strictly verified by stable ID and title.
 * Never returns a poster or metadata belonging to a different film.
 */
export function getMovieMedia(movie) {
  if (!movie) return null;

  // 1. Direct fields on the API object if present
  if (
    movie.poster_url ||
    movie.poster_path ||
    movie.backdrop_url ||
    movie.backdrop_path ||
    movie.overview ||
    movie.synopsis
  ) {
    return {
      tmdbId: movie.tmdb_id || null,
      matchedTitle: movie.title,
      matchedYear: movie.year || null,
      posterPath: movie.poster_path || movie.poster_url || null,
      backdropPath: movie.backdrop_path || movie.backdrop_url || null,
      overview: movie.overview || movie.synopsis || null,
      tagline: movie.tagline || null,
      runtime: movie.runtime || null,
      releaseDate: movie.release_date || null,
      director: Array.isArray(movie.director) ? movie.director : (movie.director ? [movie.director] : []),
      cast: Array.isArray(movie.cast) ? movie.cast : [],
      trailer: movie.trailer || null,
    };
  }

  // 2. Lookup by stable movie_lens_id with strict title compatibility check
  if (movie.movie_lens_id !== undefined && movie.movie_lens_id !== null) {
    const key = String(movie.movie_lens_id);
    const candidate = cachedManifest.items?.[key];
    if (candidate && isMediaCompatible(movie, candidate)) {
      return candidate;
    }
  }

  // 3. Fallback: Lookup by normalized title in title index
  if (movie.title) {
    if (!titleIndex) {
      titleIndex = buildTitleIndex(cachedManifest.items);
    }
    const parsed = parseMovieTitle(movie.title);
    const norm = normalizeTitle(parsed.title);
    if (norm && titleIndex.has(norm)) {
      const candidates = titleIndex.get(norm);
      for (const { item } of candidates) {
        if (isMediaCompatible(movie, item)) {
          return item;
        }
      }
    }
  }

  return null;
}

/**
 * Builds appropriate image URL from TMDB base and chosen size.
 *
 * @param {object|null} media - Media object returned by getMovieMedia
 * @param {number} targetWidth - Intended display width in px
 * @returns {string|null}
 */
export function posterUrl(media, targetWidth = 342) {
  if (!media || !media.posterPath) return null;
  const path = media.posterPath;
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  const base = cachedManifest.meta.imageBase || "https://image.tmdb.org/t/p/";
  let size = "w342";
  if (targetWidth <= 185) size = "w185";
  else if (targetWidth <= 342) size = "w342";
  else if (targetWidth <= 500) size = "w500";
  else size = "original";

  return `${base.replace(/\/$/, "")}/${size}/${path.replace(/^\//, "")}`;
}

/**
 * Builds appropriate backdrop image URL from TMDB base.
 *
 * @param {object|null} media - Media object returned by getMovieMedia
 * @param {number} targetWidth - Intended display width in px
 * @returns {string|null}
 */
export function backdropUrl(media, targetWidth = 1280) {
  if (!media || !media.backdropPath) return null;
  const path = media.backdropPath;
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  const base = cachedManifest.meta.imageBase || "https://image.tmdb.org/t/p/";
  let size = targetWidth <= 780 ? "w780" : "w1280";
  return `${base.replace(/\/$/, "")}/${size}/${path.replace(/^\//, "")}`;
}

/**
 * React hook to ensure manifest is loaded in components needing reactivity.
 */
export function useMovieMedia(movie) {
  const [, setTick] = useState(0);

  useEffect(() => {
    const rerender = () => setTick((t) => t + 1);
    listeners.add(rerender);
    loadMediaManifest().then(rerender);
    return () => {
      listeners.delete(rerender);
    };
  }, []);

  return getMovieMedia(movie);
}
