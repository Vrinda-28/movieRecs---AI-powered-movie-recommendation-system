import test from "node:test";
import assert from "node:assert/strict";
import { parseMovieTitle, normalizeTitle, parseGenres } from "./movieTitle.js";

test("1. Basic title with year: Toy Story (1995)", () => {
  const result = parseMovieTitle("Toy Story (1995)");
  assert.equal(result.title, "Toy Story");
  assert.equal(result.year, 1995);
  assert.equal(result.altTitle, null);
});

test("2. Trailing article: American President, The (1995)", () => {
  const result = parseMovieTitle("American President, The (1995)");
  assert.equal(result.title, "The American President");
  assert.equal(result.year, 1995);
});

test("3. Alternate title in parentheses: Nikita (La Femme Nikita) (1990)", () => {
  const result = parseMovieTitle("Nikita (La Femme Nikita) (1990)");
  assert.equal(result.title, "Nikita");
  assert.equal(result.altTitle, "La Femme Nikita");
  assert.equal(result.year, 1990);
});

test("4. Missing year: Star Wars", () => {
  const result = parseMovieTitle("Star Wars");
  assert.equal(result.title, "Star Wars");
  assert.equal(result.year, null);
});

test("5. Non-English article: Cité des enfants perdus, La (1995)", () => {
  const result = parseMovieTitle("Cité des enfants perdus, La (1995)");
  assert.equal(result.title, "La Cité des enfants perdus");
  assert.equal(result.year, 1995);
});

test("6. Title containing colon: Star Wars: Episode IV - A New Hope (1977)", () => {
  const result = parseMovieTitle("Star Wars: Episode IV - A New Hope (1977)");
  assert.equal(result.title, "Star Wars: Episode IV - A New Hope");
  assert.equal(result.year, 1977);
});

test("7. Title with trailing article 'A': Night to Remember, A (1958)", () => {
  const result = parseMovieTitle("Night to Remember, A (1958)");
  assert.equal(result.title, "A Night to Remember");
  assert.equal(result.year, 1958);
});

test("8. Normalization strips accents and leading articles for TMDB matching", () => {
  const norm1 = normalizeTitle("Amélie");
  const norm2 = normalizeTitle("Amelie");
  assert.equal(norm1, norm2);
  assert.equal(norm1, "amelie");

  const normThe = normalizeTitle("The Matrix");
  const normBase = normalizeTitle("Matrix");
  assert.equal(normThe, normBase);
});

test("9. Genre parsing", () => {
  const genres = parseGenres("Animation|Children's|Comedy");
  assert.deepEqual(genres, ["Animation", "Children's", "Comedy"]);
});
