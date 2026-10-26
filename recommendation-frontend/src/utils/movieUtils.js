/**
 * Movie utility re-exports and backwards compatibility.
 */
export { parseMovieTitle, normalizeTitle, parseGenres } from "./movieTitle.js";

// Kept only for internal legacy reference if needed, but no new component uses initials
export function getInitials(title) {
  if (!title) return "MO";
  const words = title.replace(/[^a-zA-Z0-9\s]/g, "").trim().split(/\s+/);
  if (words.length === 1) {
    return words[0].substring(0, 2).toUpperCase();
  }
  return (words[0][0] + (words[1] ? words[1][0] : "")).toUpperCase();
}
