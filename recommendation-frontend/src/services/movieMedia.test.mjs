import test from "node:test";
import assert from "node:assert/strict";
import {
  getMovieMedia,
  posterUrl,
  backdropUrl,
  isMediaCompatible,
  getFallbackPosterDataUrl,
} from "./movieMedia.js";

test("1. Stable identifier lookup: Toy Story (movie_lens_id: 1) resolves correct poster", () => {
  const movie = {
    id: 101,
    movie_lens_id: 1,
    title: "Toy Story (1995)",
    genres: "Animation|Children's|Comedy",
  };
  const media = getMovieMedia(movie);
  assert.ok(media, "Media should be found for Toy Story");
  assert.equal(media.matchedTitle, "Toy Story");
  assert.equal(media.matchedYear, 1995);
  assert.ok(media.posterPath, "Poster path must exist");
  const url = posterUrl(media);
  assert.match(url, /image\.tmdb\.org.*\/uXDfjJbdP4ijW5hWSBrPrlKpxab\.jpg/);
});

test("2. Corrected association: Se7en (movie_lens_id: 47) resolves Se7en, not 7 Days", () => {
  const movie = {
    id: 147,
    movie_lens_id: 47,
    title: "Seven (Se7en) (1995)",
    genres: "Crime|Thriller",
  };
  const media = getMovieMedia(movie);
  assert.ok(media, "Media should be found for Se7en");
  assert.equal(media.matchedTitle, "Se7en");
  assert.equal(media.matchedYear, 1995);
  assert.equal(media.posterPath, "/191nKfP0ehp3uIvWqgPbFmI4lv9.jpg");
});

test("3. Never display a poster belonging to a different film: rejects mismatched titles", () => {
  // Movie title does not match manifest item 1 (Toy Story)
  const mismatchedMovie = {
    id: 999,
    movie_lens_id: 1,
    title: "A Completely Different Film (1995)",
    genres: "Action",
  };
  const media = getMovieMedia(mismatchedMovie);
  assert.equal(media, null, "Must reject manifest item when title does not match");
});

test("4. Missing posters: movies with no retrieved poster return null from posterUrl", () => {
  const unretrievableMovie = {
    id: 501,
    movie_lens_id: 51,
    title: "Guardian Angel (1994)",
    genres: "Action|Drama",
  };
  const media = getMovieMedia(unretrievableMovie);
  const url = posterUrl(media);
  assert.equal(url, null, "posterUrl must be null so polished fallback is displayed");
});

test("5. Fallback SVG data URI generator creates valid archival card image", () => {
  const dataUrl = getFallbackPosterDataUrl({
    title: "Metropolis (1927)",
    year: 1927,
    genre: "Sci-Fi",
  });
  assert.ok(dataUrl.startsWith("data:image/svg+xml"), "Must produce svg data URL");
  assert.match(dataUrl, /Metropolis/);
  assert.match(dataUrl, /1927/);
  assert.match(dataUrl, /Sci-Fi/);
  assert.match(dataUrl, /ARCHIVAL%20RECORD/);
});

test("6. Compatibility check: isMediaCompatible validates aliases and rejects wrong years", () => {
  // Alias with un-inverted article
  assert.ok(
    isMediaCompatible(
      { title: "Usual Suspects, The (1995)" },
      { matchedTitle: "The Usual Suspects", matchedYear: 1995 }
    )
  );

  // Large year divergence rejected
  assert.equal(
    isMediaCompatible(
      { title: "The Fast and the Furious (1954)" },
      { matchedTitle: "The Fast and the Furious", matchedYear: 2001 }
    ),
    false
  );
});
