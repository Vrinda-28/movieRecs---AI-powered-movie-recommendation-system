#!/usr/bin/env node

/**
 * Script to enrich movie media using TMDB public data.
 * Fetches real TMDB posters, backdrops, overviews, taglines, cast, directors, and trailer keys.
 * Updates public/data/movieMedia.json directly.
 */

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import { parseMovieTitle, normalizeTitle } from "../src/utils/movieTitle.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const MANIFEST_PATH = path.resolve(__dirname, "../public/data/movieMedia.json");
const REPORT_PATH = path.resolve(__dirname, "media-report.json");

function curl(url) {
  const cmd = `curl -s -L -H "Accept-Language: en-US,en;q=0.9" -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" "${url}"`;
  return execSync(cmd, { encoding: "utf8", maxBuffer: 15 * 1024 * 1024 });
}

function searchMovieSlug(cleanTitle, targetYear) {
  try {
    const enc = encodeURIComponent(cleanTitle);
    const html = curl(`https://www.themoviedb.org/search/movie?query=${enc}`);
    
    // Parse result cards
    const cardRegex = /href="\/movie\/(\d+-[^"]*)"[\s\S]*?<h2[^>]*><span>([^<]+)<\/span><\/h2><\/a>[\s\S]*?<span class="release_date[^"]*">([^<]*)<\/span>/g;
    const cards = [...html.matchAll(cardRegex)];

    const cleanNorm = normalizeTitle(cleanTitle);

    // 1. First pass: exact title match AND year match
    for (const c of cards) {
      const slug = c[1];
      const title = c[2];
      const dateStr = c[3];
      const candYear = parseInt((dateStr.match(/\d{4}/) || [])[0], 10);
      const titleNorm = normalizeTitle(title);

      if (titleNorm === cleanNorm && targetYear && candYear === targetYear) {
        return slug;
      }
    }

    // 2. Second pass: exact title match
    for (const c of cards) {
      const slug = c[1];
      const title = c[2];
      const titleNorm = normalizeTitle(title);

      if (titleNorm === cleanNorm) {
        return slug;
      }
    }

    // 3. Third pass: check if normalized titles are close substrings with matching year
    for (const c of cards) {
      const slug = c[1];
      const title = c[2];
      const dateStr = c[3];
      const candYear = parseInt((dateStr.match(/\d{4}/) || [])[0], 10);
      const titleNorm = normalizeTitle(title);

      if (
        (cleanNorm.includes(titleNorm) || titleNorm.includes(cleanNorm)) &&
        targetYear &&
        Math.abs(candYear - targetYear) <= 1
      ) {
        return slug;
      }
    }
  } catch (err) {
    console.warn(`Search error for ${cleanTitle}: ${err.message}`);
  }
  return null;
}

function fetchMovieDetails(slug) {
  try {
    const html = curl(`https://www.themoviedb.org/movie/${slug}`);

    const idMatch = slug.match(/^(\d+)/);
    const tmdbId = idMatch ? parseInt(idMatch[1], 10) : null;

    const posterMatch = html.match(/https:\/\/media\.themoviedb\.org\/t\/p\/w500(\/[^"\s]+)/);
    const backdropMatch = html.match(/https:\/\/media\.themoviedb\.org\/t\/p\/w780(\/[^"\s]+)/);
    const descMatch = html.match(/<meta property="og:description" content="([^"]+)"/);
    const trailerMatch = html.match(/data-site="YouTube" data-id="([A-Za-z0-9_-]{11})"/);
    const titleMatch = html.match(/<meta property="og:title" content="([^"]+)"/);
    const taglineMatch = html.match(/<h3 class="tagline"[^>]*>([^<]+)<\/h3>/);

    // Director
    const dirMatches = [...html.matchAll(/<p><a href="\/person\/[^"]+">([^<]+)<\/a><\/p>\s*<p class="character">([^<]*Director[^<]*)<\/p>/g)];
    const directors = dirMatches.map((m) => m[1].trim());

    // Cast (top 5)
    const castMatches = [...html.matchAll(/<li class="card">[\s\S]*?<p><a href="\/person\/[^"]+">([^<]+)<\/a><\/p>\s*<p class="character">([^<]+)<\/p>/g)];
    const cast = castMatches.slice(0, 5).map((m) => ({
      name: m[1].trim(),
      character: m[2].trim(),
    }));

    return {
      tmdbId,
      matchedTitle: titleMatch ? titleMatch[1].trim() : null,
      posterPath: posterMatch ? posterMatch[1] : null,
      backdropPath: backdropMatch ? backdropMatch[1] : null,
      overview: descMatch ? descMatch[1].trim() : null,
      tagline: taglineMatch ? taglineMatch[1].trim() : null,
      director: directors.length > 0 ? directors : [],
      cast,
      trailer: trailerMatch ? {
        site: "YouTube",
        key: trailerMatch[1],
        name: `${titleMatch ? titleMatch[1].trim() : "Movie"} Official Trailer`,
      } : null,
    };
  } catch (err) {
    console.warn(`Fetch error for ${slug}: ${err.message}`);
    return null;
  }
}

async function run() {
  // Parse args
  const args = process.argv.slice(2);
  let batchSize = Infinity; // process all by default
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--batch" && args[i + 1]) {
      batchSize = parseInt(args[i + 1], 10) || Infinity;
      i++;
    }
  }

  console.log("Enriching movie media manifest...");
  let manifest = {
    meta: {
      imageBase: "https://image.tmdb.org/t/p/",
      posterSizes: ["w185", "w342", "w500", "original"],
      backdropSizes: ["w780", "w1280", "original"],
      generatedAt: new Date().toISOString(),
      source: "TMDB",
    },
    items: {},
  };

  try {
    const existing = JSON.parse(await fs.readFile(MANIFEST_PATH, "utf8"));
    if (existing && existing.items) manifest.items = existing.items;
  } catch {}

  // Fetch ALL movies from local backend
  const apiRes = await fetch("http://127.0.0.1:8000/api/v1/movies/?limit=5000");
  const allMovies = await apiRes.json();
  console.log(`Fetched ${allMovies.length} total movies from API`);

  // Filter to only unenriched ones (skip those that already have poster + overview)
  const unenriched = allMovies.filter((m) => {
    const key = String(m.movie_lens_id ?? m.id);
    const existing = manifest.items[key];
    return !existing || !existing.posterPath || !existing.overview;
  });

  // Apply batch limit
  const targetMovies = unenriched.slice(0, batchSize);
  console.log(`${unenriched.length} unenriched, processing ${targetMovies.length} in this run\n`);

  let enrichedCount = 0;
  for (const movie of targetMovies) {
    const mlIdStr = String(movie.movie_lens_id ?? movie.id);

    const { title: cleanTitle, year } = parseMovieTitle(movie.title);
    process.stdout.write(`[${enrichedCount + 1}/${targetMovies.length}] "${cleanTitle}" (${year || "?"})... `);

    const slug = searchMovieSlug(cleanTitle, year);
    if (!slug) {
      console.log(`NO MATCH`);
      // Store empty marker so we don't retry this one
      manifest.items[mlIdStr] = manifest.items[mlIdStr] || {
        tmdbId: null,
        matchedTitle: cleanTitle,
        matchedYear: year,
        posterPath: null,
        backdropPath: null,
        overview: null,
        tagline: null,
        director: [],
        cast: [],
        trailer: null,
      };
      continue;
    }

    const details = fetchMovieDetails(slug);
    if (!details) {
      console.log(`FETCH ERROR`);
      continue;
    }

    manifest.items[mlIdStr] = {
      tmdbId: details.tmdbId,
      matchedTitle: details.matchedTitle || cleanTitle,
      matchedYear: year,
      posterPath: details.posterPath,
      backdropPath: details.backdropPath,
      overview: details.overview,
      tagline: details.tagline,
      director: details.director,
      cast: details.cast,
      trailer: details.trailer,
    };

    enrichedCount++;
    console.log(`OK (poster:${Boolean(details.posterPath)}, trailer:${details.trailer ? details.trailer.key : "none"})`);

    // Save progress every 10 movies
    if (enrichedCount % 10 === 0) {
      manifest.meta.generatedAt = new Date().toISOString();
      await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2), "utf8");
      process.stdout.write(`[Saved progress: ${enrichedCount} enriched so far]\n`);
    }
  }

  manifest.meta.generatedAt = new Date().toISOString();
  await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2), "utf8");
  const totalInManifest = Object.keys(manifest.items).length;
  console.log(`\nDone! Enriched ${enrichedCount} in this batch. Total in manifest: ${totalInManifest}. Remaining unenriched: ${unenriched.length - targetMovies.length}`);
}

run().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
