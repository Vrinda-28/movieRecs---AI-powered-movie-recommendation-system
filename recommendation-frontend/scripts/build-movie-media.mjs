#!/usr/bin/env node

/**
 * Build script to generate static movie media manifest from TMDB.
 * Zero external dependencies: uses Node 18+ built-in fetch and fs/promises.
 *
 * Reads TMDB_API_KEY or TMDB_READ_TOKEN from environment variables only.
 */

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseMovieTitle, normalizeTitle } from "../src/utils/movieTitle.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PUBLIC_DATA_DIR = path.resolve(__dirname, "../public/data");
const MANIFEST_PATH = path.join(PUBLIC_DATA_DIR, "movieMedia.json");
const REPORT_PATH = path.join(__dirname, "media-report.json");
const FALLBACK_MOVIES_DAT = path.resolve(__dirname, "../../data/ml-1m/movies.dat");

const TMDB_API_BASE = "https://api.themoviedb.org/3";
const API_KEY = process.env.TMDB_API_KEY;
const READ_TOKEN = process.env.TMDB_READ_TOKEN;

// Parse CLI arguments
const args = process.argv.slice(2);
let limit = 500;
let force = false;

for (let i = 0; i < args.length; i++) {
  if (args[i] === "--limit" && args[i + 1]) {
    limit = parseInt(args[i + 1], 10) || 500;
    i++;
  } else if (args[i] === "--force") {
    force = true;
  }
}

async function ensureDir(dirPath) {
  try {
    await fs.mkdir(dirPath, { recursive: true });
  } catch {
    // Ignore already exists
  }
}

function getAuthHeaders() {
  if (READ_TOKEN) {
    return {
      Authorization: `Bearer ${READ_TOKEN}`,
      Accept: "application/json",
    };
  }
  return { Accept: "application/json" };
}

function getUrlWithKey(urlStr) {
  const url = new URL(urlStr);
  if (!READ_TOKEN && API_KEY) {
    url.searchParams.set("api_key", API_KEY);
  }
  return url.toString();
}

async function tmdbFetch(urlStr, retries = 3) {
  const fullUrl = getUrlWithKey(urlStr);
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const res = await fetch(fullUrl, { headers: getAuthHeaders() });
      if (res.status === 429) {
        const retryAfter = parseInt(res.headers.get("retry-after") || "1", 10);
        console.warn(`[TMDB Rate Limited] Sleeping ${retryAfter}s...`);
        await new Promise((r) => setTimeout(r, retryAfter * 1000 + 200));
        continue;
      }
      if (!res.ok) {
        if (attempt === retries - 1) {
          throw new Error(`TMDB HTTP error ${res.status}: ${res.statusText}`);
        }
        await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
        continue;
      }
      return await res.json();
    } catch (err) {
      if (attempt === retries - 1) throw err;
      await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
    }
  }
}

async function fetchMoviesCatalogue() {
  console.log("Fetching movies from running API (http://127.0.0.1:8000)...");
  try {
    const res = await fetch("http://127.0.0.1:8000/api/v1/movies/?limit=5000", {
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      const data = await res.json();
      console.log(`Loaded ${data.length} movies from live API.`);
      return data;
    }
  } catch (err) {
    console.warn(`Could not reach live API: ${err.message}. Falling back to movies.dat...`);
  }

  // Fallback to ../data/ml-1m/movies.dat
  try {
    const rawDat = await fs.readFile(FALLBACK_MOVIES_DAT, "latin1");
    const lines = rawDat.split("\n").filter(Boolean);
    const movies = lines.map((line) => {
      const [mlId, title, genres] = line.split("::");
      return {
        id: parseInt(mlId, 10),
        movie_lens_id: parseInt(mlId, 10),
        title: title ? title.trim() : "",
        genres: genres ? genres.trim() : "",
        num_ratings: 1, // Fallback rank
      };
    });
    console.log(`Loaded ${movies.length} movies from ${FALLBACK_MOVIES_DAT}.`);
    return movies;
  } catch (datErr) {
    console.error("Failed to load movies from fallback data file:", datErr.message);
    return [];
  }
}

async function run() {
  await ensureDir(PUBLIC_DATA_DIR);

  if (!API_KEY && !READ_TOKEN) {
    console.log("------------------------------------------------------------------");
    console.log("Notice: No TMDB_API_KEY or TMDB_READ_TOKEN provided in environment.");

    let existingItems = {};
    try {
      const existing = JSON.parse(await fs.readFile(MANIFEST_PATH, "utf8"));
      if (existing && existing.items && !force) {
        existingItems = existing.items;
      }
    } catch {}

    const itemCount = Object.keys(existingItems).length;
    if (itemCount > 0) {
      console.log(`Preserving ${itemCount} existing curated movie media entries.`);
      console.log("------------------------------------------------------------------");
      return;
    }

    console.log("Writing valid empty manifest and report. All components will safely");
    console.log("render high-fidelity editorial fallback states (PosterFallback & TrailerUnavailable).");
    console.log("------------------------------------------------------------------");

    const emptyManifest = {
      meta: {
        imageBase: "https://image.tmdb.org/t/p/",
        posterSizes: ["w185", "w342", "w500", "original"],
        backdropSizes: ["w780", "w1280", "original"],
        generatedAt: new Date().toISOString(),
        source: "TMDB",
      },
      items: {},
    };

    const emptyReport = {
      matchedCount: 0,
      unmatchedCount: 0,
      trailerCount: 0,
      generatedAt: new Date().toISOString(),
      items: {},
    };

    await fs.writeFile(MANIFEST_PATH, JSON.stringify(emptyManifest, null, 2), "utf8");
    await fs.writeFile(REPORT_PATH, JSON.stringify(emptyReport, null, 2), "utf8");
    console.log(`Wrote empty manifest to ${MANIFEST_PATH}`);
    console.log(`Wrote empty report to ${REPORT_PATH}`);
    return;
  }

  // Fetch configuration from TMDB
  console.log("Fetching TMDB configuration...");
  const config = await tmdbFetch(`${TMDB_API_BASE}/configuration`);
  const imageBase = config.images?.secure_base_url || "https://image.tmdb.org/t/p/";
  const posterSizes = config.images?.poster_sizes || ["w185", "w342", "w500", "original"];
  const backdropSizes = config.images?.backdrop_sizes || ["w780", "w1280", "original"];

  // Read existing manifest if any for resumable build
  let manifest = {
    meta: {
      imageBase,
      posterSizes,
      backdropSizes,
      generatedAt: new Date().toISOString(),
      source: "TMDB",
    },
    items: {},
  };

  if (!force) {
    try {
      const existing = JSON.parse(await fs.readFile(MANIFEST_PATH, "utf8"));
      if (existing && existing.items) {
        manifest = existing;
        manifest.meta.generatedAt = new Date().toISOString();
        console.log(`Loaded existing manifest with ${Object.keys(manifest.items).length} items.`);
      }
    } catch {
      // Start fresh
    }
  }

  const allMovies = await fetchMoviesCatalogue();
  if (!allMovies.length) {
    console.error("No movies available to enrich.");
    return;
  }

  // Sort by num_ratings descending
  const sorted = [...allMovies].sort((a, b) => (b.num_ratings || 0) - (a.num_ratings || 0));

  // Top N selection, ensuring Toy Story (id: 1) is included
  const selectedMap = new Map();
  for (const m of sorted.slice(0, limit)) {
    selectedMap.set(m.movie_lens_id, m);
  }
  const toyStory = allMovies.find((m) => m.movie_lens_id === 1);
  if (toyStory) selectedMap.set(1, toyStory);

  const moviesToProcess = Array.from(selectedMap.values());
  console.log(`Processing ${moviesToProcess.length} movies for TMDB enrichment...`);

  const report = {
    matchedCount: 0,
    unmatchedCount: 0,
    trailerCount: 0,
    generatedAt: new Date().toISOString(),
    items: {},
  };

  let processedCount = 0;

  for (const movie of moviesToProcess) {
    processedCount++;
    const mlIdStr = String(movie.movie_lens_id);

    // Skip if already matched unless force
    if (!force && manifest.items[mlIdStr]) {
      report.matchedCount++;
      if (manifest.items[mlIdStr].trailer) report.trailerCount++;
      continue;
    }

    const { title: cleanTitle, year: mlYear, altTitle } = parseMovieTitle(movie.title);
    const normClean = normalizeTitle(cleanTitle);
    const normAlt = altTitle ? normalizeTitle(altTitle) : null;

    // Rate-limit pause (~100ms for ~10 req/s)
    await new Promise((r) => setTimeout(r, 100));

    try {
      // Search TMDB
      const searchUrl = new URL(`${TMDB_API_BASE}/search/movie`);
      searchUrl.searchParams.set("query", cleanTitle);
      if (mlYear) {
        searchUrl.searchParams.set("primary_release_year", String(mlYear));
      }

      const searchRes = await tmdbFetch(searchUrl.toString());
      const results = searchRes.results || [];

      // Strict matching criteria
      const matchingCandidates = results.filter((cand) => {
        const candYear = cand.release_date ? parseInt(cand.release_date.slice(0, 4), 10) : null;
        if (mlYear && candYear && candYear !== mlYear) return false;

        const candTitleNorm = normalizeTitle(cand.title);
        const candOrigNorm = normalizeTitle(cand.original_title);

        const titleMatches =
          candTitleNorm === normClean ||
          candOrigNorm === normClean ||
          (normAlt && (candTitleNorm === normAlt || candOrigNorm === normAlt));

        return Boolean(titleMatches);
      });

      if (!matchingCandidates.length) {
        report.unmatchedCount++;
        report.items[mlIdStr] = {
          status: "unmatched",
          mlTitle: movie.title,
          cleanTitle,
          mlYear,
          topCandidates: results.slice(0, 3).map((c) => ({
            id: c.id,
            title: c.title,
            release_date: c.release_date,
            vote_count: c.vote_count,
          })),
        };
        continue;
      }

      // Pick highest vote_count
      matchingCandidates.sort((a, b) => (b.vote_count || 0) - (a.vote_count || 0));
      const chosen = matchingCandidates[0];

      // Fetch detailed data with credits and videos
      await new Promise((r) => setTimeout(r, 100));
      const details = await tmdbFetch(
        `${TMDB_API_BASE}/movie/${chosen.id}?append_to_response=credits,videos`,
      );

      // Extract director(s)
      const directors = (details.credits?.crew || [])
        .filter((c) => c.job === "Director")
        .map((c) => c.name);

      // Extract first 6 cast members
      const cast = (details.credits?.cast || []).slice(0, 6).map((c) => ({
        name: c.name,
        character: c.character,
      }));

      // Extract best trailer
      const videos = details.videos?.results || [];
      const ytVideos = videos.filter(
        (v) => v.site === "YouTube" && /^[A-Za-z0-9_-]{11}$/.test(v.key),
      );

      let bestTrailer = null;
      if (ytVideos.length > 0) {
        // Preference: Trailer -> Official -> Newest
        ytVideos.sort((a, b) => {
          if (a.type === "Trailer" && b.type !== "Trailer") return -1;
          if (b.type === "Trailer" && a.type !== "Trailer") return 1;
          if (a.official && !b.official) return -1;
          if (b.official && !a.official) return 1;
          return new Date(b.published_at || 0) - new Date(a.published_at || 0);
        });
        bestTrailer = {
          key: ytVideos[0].key,
          name: ytVideos[0].name,
        };
      }

      const mediaEntry = {
        tmdbId: details.id,
        matchedTitle: details.title,
        matchedYear: details.release_date ? parseInt(details.release_date.slice(0, 4), 10) : mlYear,
        posterPath: details.poster_path || null,
        backdropPath: details.backdrop_path || null,
        overview: details.overview || null,
        tagline: details.tagline || null,
        runtime: details.runtime || null,
        releaseDate: details.release_date || null,
        director: directors,
        cast,
        trailer: bestTrailer,
      };

      manifest.items[mlIdStr] = mediaEntry;
      report.matchedCount++;
      if (bestTrailer) report.trailerCount++;

      report.items[mlIdStr] = {
        status: "matched",
        mlTitle: movie.title,
        matchedTitle: details.title,
        tmdbId: details.id,
        hasPoster: Boolean(details.poster_path),
        hasBackdrop: Boolean(details.backdrop_path),
        trailer: bestTrailer ? bestTrailer.name : null,
      };

      if (processedCount % 25 === 0) {
        console.log(`[Progress ${processedCount}/${moviesToProcess.length}] Matched: ${report.matchedCount}, Unmatched: ${report.unmatchedCount}`);
        await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2), "utf8");
      }
    } catch (movieErr) {
      console.warn(`Error enriching ${movie.title}: ${movieErr.message}`);
    }
  }

  await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2), "utf8");
  await fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");

  console.log("------------------------------------------------------------------");
  console.log(`Done! Matched: ${report.matchedCount}, Unmatched: ${report.unmatchedCount}, Trailers: ${report.trailerCount}`);
  console.log(`Saved manifest to ${MANIFEST_PATH}`);
  console.log(`Saved report to ${REPORT_PATH}`);
}

run().catch((err) => {
  console.error("Fatal error in build-movie-media:", err);
  process.exit(1);
});
