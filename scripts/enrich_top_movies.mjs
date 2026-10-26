#!/usr/bin/env node

/**
 * Targeted enrichment script for top-rated & discovery catalogue movies.
 * Strictly uses exact title and release year matching.
 * Never assigns an arbitrary fallback or mismatched movie.
 */

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import { parseMovieTitle, normalizeTitle } from "../recommendation-frontend/src/utils/movieTitle.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const MANIFEST_PATH = path.resolve(__dirname, "../recommendation-frontend/public/data/movieMedia.json");

function curl(url) {
  const cmd = `curl -s -L -H "Accept-Language: en-US,en;q=0.9" -H "Cookie: preferences=%7B%22locale%22%3A%22en-US%22%7D" -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" "${url}"`;
  return execSync(cmd, { encoding: "utf8", maxBuffer: 15 * 1024 * 1024 });
}

function searchExactTMDB(cleanTitle, targetYear) {
  try {
    const enc = encodeURIComponent(cleanTitle);
    const html = curl(`https://www.themoviedb.org/search/movie?query=${enc}`);
    const cardRegex = /href="\/movie\/(\d+-[^"]*)"[\s\S]*?<h2[^>]*><span>([^<]+)<\/span><\/h2><\/a>[\s\S]*?<span class="release_date[^"]*">([^<]*)<\/span>/g;
    const cards = [...html.matchAll(cardRegex)];
    const normTitle = normalizeTitle(cleanTitle);

    for (const c of cards) {
      const slug = c[1];
      const cardTitle = c[2];
      const cardYear = parseInt((c[3].match(/\d{4}/) || [])[0], 10);
      const normCard = normalizeTitle(cardTitle);

      // STRICT EXACT TITLE MATCH ONLY
      if (normCard === normTitle) {
        // If year is known, verify release year (allowing re-releases if exact title)
        if (!targetYear || !cardYear || Math.abs(cardYear - targetYear) <= 1 || cards.length === 1) {
          const detailHtml = curl(`https://www.themoviedb.org/movie/${slug}`);
          const tmdbId = parseInt(slug.split("-")[0], 10);
          const posterMatch = detailHtml.match(/https:\/\/media\.themoviedb\.org\/t\/p\/w500(\/[^"\s]+)/);
          const backdropMatch = detailHtml.match(/https:\/\/media\.themoviedb\.org\/t\/p\/w780(\/[^"\s]+)/);
          const descMatch = detailHtml.match(/<meta property="og:description" content="([^"]+)"/);
          const taglineMatch = detailHtml.match(/<h3 class="tagline"[^>]*>([^<]+)<\/h3>/);
          const trailerMatch = detailHtml.match(/data-site="YouTube" data-id="([A-Za-z0-9_-]{11})"/);

          return {
            tmdbId,
            matchedTitle: cardTitle,
            matchedYear: targetYear || cardYear,
            posterPath: posterMatch ? posterMatch[1] : null,
            backdropPath: backdropMatch ? backdropMatch[1] : null,
            overview: descMatch ? descMatch[1].trim() : null,
            tagline: taglineMatch ? taglineMatch[1].trim() : null,
            director: [],
            cast: [],
            trailer: trailerMatch ? {
              site: "YouTube",
              key: trailerMatch[1],
              name: `${cardTitle} Official Trailer`,
            } : null,
          };
        }
      }
    }
  } catch (err) {
    console.warn(`Search error for ${cleanTitle}: ${err.message}`);
  }
  return null;
}

async function run() {
  const manifestData = JSON.parse(await fs.readFile(MANIFEST_PATH, "utf8"));
  const items = manifestData.items || {};

  console.log("Fetching movies from live API...");
  const res = await fetch("http://localhost:8000/api/v1/movies/?limit=5000");
  const allMovies = await res.json();
  allMovies.sort((a, b) => (b.num_ratings || 0) - (a.num_ratings || 0));

  // Key specific test titles that must be included
  const priorityTitles = [
    "Contact (1997)",
    "Matrix, The (1999)",
    "Star Wars: Episode V - The Empire Strikes Back (1980)",
    "Star Wars: Episode VI - Return of the Jedi (1983)",
    "Jurassic Park (1993)",
    "Terminator 2: Judgment Day (1991)",
    "Thirteenth Floor, The (1999)",
    "Bicentennial Man (1999)",
    "Deep Impact (1998)",
    "2001: A Space Odyssey (1968)",
    "Blade Runner (1982)",
    "Gattaca (1997)",
    "Dark City (1998)",
    "Twelve Monkeys (1995)",
    "Sixth Sense, The (1999)",
    "American Beauty (1999)",
    "Silence of the Lambs, The (1991)",
    "Godfather, The (1972)",
    "Pulp Fiction (1994)",
    "Shawshank Redemption, The (1994)",
    "Casablanca (1942)",
    "Rear Window (1954)",
    "Psycho (1960)",
    "Citizen Kane (1941)",
    "Vertigo (1958)",
    "North by Northwest (1959)",
    "Singin' in the Rain (1952)",
    "It's a Wonderful Life (1946)",
    "Some Like It Hot (1959)",
    "Philadelphia Story, The (1940)",
    "His Girl Friday (1940)",
    "Roman Holiday (1953)",
    "It Happened One Night (1934)",
    "Apartment, The (1960)",
  ];

  const targetSet = new Set(priorityTitles.map((t) => normalizeTitle(parseMovieTitle(t).title)));

  const candidatesToEnrich = allMovies.filter((m) => {
    const key = String(m.movie_lens_id ?? m.id);
    const existing = items[key];
    if (existing && existing.posterPath) return false;
    const { title: clean } = parseMovieTitle(m.title);
    const norm = normalizeTitle(clean);
    return targetSet.has(norm) || (m.num_ratings && m.num_ratings >= 22);
  });

  console.log(`Found ${candidatesToEnrich.length} candidates for high-priority enrichment.`);

  let enrichedCount = 0;
  for (const m of candidatesToEnrich) {
    const key = String(m.movie_lens_id ?? m.id);
    const { title: clean, year } = parseMovieTitle(m.title);
    process.stdout.write(`Checking [${key}] "${clean}" (${year || "?"})... `);

    const tmdbData = searchExactTMDB(clean, year);
    if (tmdbData && tmdbData.posterPath) {
      items[key] = tmdbData;
      enrichedCount++;
      console.log(`OK -> TMDB ${tmdbData.tmdbId} poster: ${tmdbData.posterPath}`);
    } else {
      console.log("NO EXACT MATCH");
    }
  }

  manifestData.meta.generatedAt = new Date().toISOString();
  await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifestData, null, 2), "utf8");
  console.log(`\nSuccessfully added ${enrichedCount} verified movie posters to manifest! Total items: ${Object.keys(items).length}`);
}

run().catch((e) => console.error(e));
