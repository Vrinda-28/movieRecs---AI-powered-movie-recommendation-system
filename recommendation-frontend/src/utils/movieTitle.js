/**
 * Movie title parsing and normalization utilities.
 * Pure ESM: importable in both Vite and Node.js without dependencies.
 */

// Trailing articles in English and major European languages found in MovieLens
const TRAILING_ARTICLE_REGEX =
  /^(.*?),\s*(The|A|An|Les|La|Le|L'|Il|Lo|Gli|I|Das|Der|Die|Ein|Eine|El|Los|Las)\s*$/i;

/**
 * Parses a MovieLens raw title string (e.g. "American President, The (1995)").
 * Extracts the 4-digit release year, un-inverts trailing articles,
 * and extracts parenthesised alternate titles.
 *
 * @param {string} rawTitle - Raw title from database/catalogue
 * @returns {{ title: string, year: number | null, cleanTitle: string, altTitle: string | null, rawTitle: string }}
 */
export function parseMovieTitle(rawTitle) {
  if (!rawTitle || typeof rawTitle !== "string") {
    return {
      title: "Untitled",
      year: null,
      cleanTitle: "Untitled",
      altTitle: null,
      rawTitle: rawTitle || "",
    };
  }

  const trimmed = rawTitle.trim();
  let working = trimmed;
  let year = null;

  // Extract year at end of string: "(1995)"
  const yearMatch = working.match(/\s*\((\d{4})\)\s*$/);
  if (yearMatch) {
    year = parseInt(yearMatch[1], 10);
    working = working.replace(/\s*\(\d{4}\)\s*$/, "").trim();
  }

  // Check for parenthesised alternate title: e.g. "Nikita (La Femme Nikita)"
  let altTitle = null;
  const altMatch = working.match(/\s*\(([^)]+)\)\s*$/);
  if (altMatch) {
    altTitle = altMatch[1].trim();
    working = working.replace(/\s*\([^)]+\)\s*$/, "").trim();
  }

  // Un-invert trailing articles: e.g. "American President, The" -> "The American President"
  let mainTitle = working;
  const articleMatch = mainTitle.match(TRAILING_ARTICLE_REGEX);
  if (articleMatch) {
    const base = articleMatch[1].trim();
    const article = articleMatch[2].trim();
    mainTitle = `${article} ${base}`.trim();
  }

  // Also un-invert altTitle if it has a trailing article: "Femme Nikita, La"
  if (altTitle) {
    const altArticleMatch = altTitle.match(TRAILING_ARTICLE_REGEX);
    if (altArticleMatch) {
      altTitle = `${altArticleMatch[2].trim()} ${altArticleMatch[1].trim()}`.trim();
    }
  }

  return {
    title: mainTitle,
    year,
    cleanTitle: mainTitle,
    altTitle,
    rawTitle: trimmed,
  };
}

/**
 * Normalizes a movie title for strict string comparison against TMDB results.
 * Strips accents/diacritics, removes leading articles, punctuation, and extra whitespace.
 *
 * @param {string} str - Title string to normalize
 * @returns {string}
 */
export function normalizeTitle(str) {
  if (!str || typeof str !== "string") return "";

  let norm = str
    .trim()
    .toLowerCase()
    // Decompose Unicode accents
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    // Remove leading English articles for comparison flexibility
    .replace(/^(the|a|an)\s+/i, "")
    // Remove common punctuation except letters and digits
    .replace(/[^a-z0-9\s]/g, " ")
    // Collapse whitespace
    .replace(/\s+/g, " ")
    .trim();

  return norm;
}

/**
 * Formats genre pipe-delimited string into an array of clean genre names.
 *
 * @param {string} genresStr - e.g. "Animation|Children's|Comedy"
 * @returns {string[]}
 */
export function parseGenres(genresStr) {
  if (!genresStr || typeof genresStr !== "string") return [];
  return genresStr
    .split("|")
    .map((g) => g.trim())
    .filter(Boolean);
}
