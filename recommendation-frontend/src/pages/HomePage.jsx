import React, { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useAppContext } from "../contexts/AppContext";
import ApiService from "../services/ApiService";
import HeroMovie from "../components/Common/HeroMovie";
import SectionRow from "../components/Common/SectionRow";
import GenreBadge from "../components/Common/GenreBadge";
import MovieGrid from "../components/Common/MovieGrid";
import RatingModal from "../components/Common/RatingModal";
import AiPromptPanel from "../components/Common/AiPromptPanel";
import { Search, X } from "lucide-react";
import { getMovieMedia, backdropUrl } from "../services/movieMedia";

const POPULAR_GENRES = [
  "Action",
  "Adventure",
  "Animation",
  "Comedy",
  "Crime",
  "Documentary",
  "Drama",
  "Fantasy",
  "Film-Noir",
  "Horror",
  "Musical",
  "Mystery",
  "Romance",
  "Sci-Fi",
  "Thriller",
  "War",
  "Western",
];

// Debounce helper
function debounce(func, delay) {
  let timeout;
  return function executedFunction(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), delay);
  };
}

const HomePage = () => {
  const { isAuthenticated, token } = useAuth();
  const { navigateTo, showGlobalMessage } = useAppContext();

  // State for Hero & Curated Sections
  const [heroMovie, setHeroMovie] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [loadingRecs, setLoadingRecs] = useState(true);
  const [isPersonalizedRecs, setIsPersonalizedRecs] = useState(false);

  const [mostRatedMovies, setMostRatedMovies] = useState([]);
  const [loadingMostRated, setLoadingMostRated] = useState(true);

  // State for Full Catalogue
  const [catalogueMovies, setCatalogueMovies] = useState([]);
  const [loadingCatalogue, setLoadingCatalogue] = useState(true);
  const [catalogueError, setCatalogueError] = useState("");
  const [currentPageNum, setCurrentPageNum] = useState(0);
  const [hasMoreCatalogue, setHasMoreCatalogue] = useState(true);
  const moviesPerPage = 12;

  // Search & Filter State
  const [searchTerm, setSearchTerm] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [selectedGenres, setSelectedGenres] = useState([]);

  // Rating Modal
  const [showRatingModalFor, setShowRatingModalFor] = useState(null);

  const catalogueRef = useRef(null);

  // 1. Fetch Recommendations for Section 2
  const fetchRecommendations = useCallback(async () => {
    setLoadingRecs(true);
    try {
      if (isAuthenticated && token) {
        const data = await ApiService.getMyRecommendations(token, 10);
        if (data && data.length > 0) {
          setRecommendations(data);
          const hasPersonalized = data.some((r) => r.is_personalized === true);
          setIsPersonalizedRecs(hasPersonalized);
        } else {
          setRecommendations([]);
          setIsPersonalizedRecs(false);
        }
      } else {
        // Guest cold-start: popular items
        const guestData = await ApiService.getMovies(0, 10);
        setRecommendations(guestData ? guestData.map(m => ({ ...m, is_personalized: false })) : []);
        setIsPersonalizedRecs(false);
      }
    } catch (err) {
      console.warn("Failed to fetch recommendations section:", err);
      setRecommendations([]);
    } finally {
      setLoadingRecs(false);
    }
  }, [isAuthenticated, token]);

  // 2. Fetch Most-Rated Movies & Pick Hero deterministically
  const fetchMostRatedAndHero = useCallback(async () => {
    setLoadingMostRated(true);
    try {
      const data = await ApiService.getMovies(0, 24, token);
      if (data && data.length > 0) {
        setMostRatedMovies(data);

        // Deterministic Hero selection:
        // Highest num_ratings movie that has a backdrop; fallback to highest num_ratings
        const withBackdrop = data.find((m) => {
          const media = getMovieMedia(m);
          return Boolean(backdropUrl(media, 780));
        });

        const chosenHero = withBackdrop || data[0];
        setHeroMovie(chosenHero);
      }
    } catch (err) {
      console.warn("Failed to fetch most rated movies:", err);
    } finally {
      setLoadingMostRated(false);
    }
  }, [token]);

  // 3. Fetch Full Catalogue with Search & Filter for Section 5
  const fetchCatalogue = useCallback(
    async (pageNum, searchVal, genresList, isReset = false) => {
      setLoadingCatalogue(true);
      setCatalogueError("");

      if (isReset) {
        setCatalogueMovies([]);
      }

      try {
        const genresParam = genresList.length > 0 ? genresList.join(",") : null;
        const data = await ApiService.getMovies(
          pageNum * moviesPerPage,
          moviesPerPage,
          token,
          searchVal || null,
          genresParam,
        );

        if (data && data.length > 0) {
          setCatalogueMovies((prev) => (isReset ? data : [...prev, ...data]));
          setHasMoreCatalogue(data.length === moviesPerPage);
        } else {
          if (pageNum === 0) {
            setCatalogueMovies([]);
          }
          setHasMoreCatalogue(false);
        }
      } catch (err) {
        setCatalogueError(
          err.isNetworkError
            ? "Backend connection offline. Please check if the recommendation service is running."
            : err.message || "Failed to load movie catalogue.",
        );
        if (isReset) setCatalogueMovies([]);
        setHasMoreCatalogue(false);
      } finally {
        setLoadingCatalogue(false);
      }
    },
    [token, moviesPerPage],
  );

  // Debounced search handler
  const debouncedSearchRef = useRef(
    debounce((query) => {
      setCurrentPageNum(0);
      setActiveSearch(query);
    }, 400),
  );

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearchTerm(val);
    debouncedSearchRef.current(val);
  };

  const clearSearch = () => {
    setSearchTerm("");
    setActiveSearch("");
  };

  // Toggle Genre in Filter
  const toggleGenre = (genre) => {
    setSelectedGenres((prev) => {
      const next = prev.includes(genre)
        ? prev.filter((g) => g !== genre)
        : [...prev, genre];
      return next;
    });
    setCurrentPageNum(0);

    if (catalogueRef.current) {
      catalogueRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const clearAllGenres = () => {
    setSelectedGenres([]);
    setCurrentPageNum(0);
  };

  useEffect(() => {
    fetchRecommendations();
    fetchMostRatedAndHero();
  }, [fetchRecommendations, fetchMostRatedAndHero]);

  useEffect(() => {
    setCurrentPageNum(0);
    fetchCatalogue(0, activeSearch, selectedGenres, true);
  }, [activeSearch, selectedGenres, fetchCatalogue]);

  const handleLoadMore = () => {
    const nextPage = currentPageNum + 1;
    setCurrentPageNum(nextPage);
    fetchCatalogue(nextPage, activeSearch, selectedGenres, false);
  };

  const handleCardClick = (movieId) => {
    navigateTo("movieDetail", movieId);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleRateMovieClick = (movie) => {
    if (!isAuthenticated) {
      showGlobalMessage("Please log in to rate movies.", "error");
      navigateTo("login");
      return;
    }
    setShowRatingModalFor(movie);
  };

  const handleRatingModalClose = () => {
    setShowRatingModalFor(null);
    fetchRecommendations();
    fetchCatalogue(currentPageNum, activeSearch, selectedGenres, true);
  };

  return (
    <div className="w-full">
      {/* ========================================================================= */}
      {/* SECTION 1: HERO MOVIE (Full-bleed)                                       */}
      {/* ========================================================================= */}
      {heroMovie && (
        <HeroMovie
          movie={heroMovie}
          onViewDetails={handleCardClick}
          onRateMovie={handleRateMovieClick}
          isAuthenticated={isAuthenticated}
        />
      )}

      {/* Main page container */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 space-y-16">
        {/* ======================================================================= */}
        {/* SECTION 2: RECOMMENDED FOR YOU                                         */}
        {/* ======================================================================= */}
        <SectionRow
          title={
            isAuthenticated
              ? isPersonalizedRecs
                ? "Recommended For You"
                : "Popular Recommendations"
              : "Discover Films"
          }
          subtitle={
            isAuthenticated
              ? isPersonalizedRecs
                ? "Personalized by your rating history using sequential GRU4Rec modeling."
                : "Popular titles based on community ratings. Rate movies to activate personalized sequential recommendations."
              : "Sign in and rate movies to unlock personalized recommendations."
          }
          badge={
            isAuthenticated
              ? isPersonalizedRecs
                ? "Personalized"
                : "Popularity Baseline"
              : "Catalogue"
          }
          movies={recommendations}
          loading={loadingRecs}
          showRank={true}
          onCardClick={handleCardClick}
          onRateMovieClick={handleRateMovieClick}
          isAuthenticated={isAuthenticated}
          emptyMessage="Rate movies in the catalogue below to generate your personalized recommendations."
        />

        {/* ======================================================================= */}
        {/* SECTION 3: BROWSE BY GENRE                                              */}
        {/* ======================================================================= */}
        <section aria-label="Browse by genre" className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2 pb-2 border-b border-[#D9D3C7]">
            <div>
              <h2 className="font-['Jost',sans-serif] font-bold text-lg sm:text-xl uppercase tracking-[0.1em] text-[#141414]">
                Browse by Genre
              </h2>
              <p className="text-xs text-[#5E5A52] font-medium mt-1">
                Filter the catalogue in real time by cinematic category
              </p>
            </div>
            {selectedGenres.length > 0 && (
              <button
                type="button"
                onClick={clearAllGenres}
                className="text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#C8412B] hover:underline self-end sm:self-auto cursor-pointer"
              >
                Clear filters ({selectedGenres.length})
              </button>
            )}
          </div>

          <div className="flex flex-wrap gap-2 p-5 bg-white border border-[#D9D3C7]">
            {POPULAR_GENRES.map((genre) => {
              const isSelected = selectedGenres.includes(genre);
              return (
                <GenreBadge
                  key={genre}
                  genre={genre}
                  active={isSelected}
                  size="md"
                  onClick={() => toggleGenre(genre)}
                />
              );
            })}
          </div>
        </section>

        {/* ======================================================================= */}
        {/* SECTION 4: MOST RATED BY MEMBERS (Honest labeling: Never "Trending")   */}
        {/* ======================================================================= */}
        <SectionRow
          title="Most Rated by Members"
          subtitle="Titles with the highest volume of community ratings across the catalogue."
          badge="Most Rated"
          movies={mostRatedMovies}
          loading={loadingMostRated}
          onCardClick={handleCardClick}
          onRateMovieClick={handleRateMovieClick}
          isAuthenticated={isAuthenticated}
        />

        {/* ======================================================================= */}
        {/* SECTION 5: EXPLORE FULL CATALOGUE                                       */}
        {/* ======================================================================= */}
        <section ref={catalogueRef} className="scroll-mt-24 space-y-6" aria-label="Explore movie catalogue">
          {/* AI Discovery Panel */}
          <AiPromptPanel
            isAuthenticated={isAuthenticated}
            token={token}
            navigateTo={navigateTo}
            onCardClick={handleCardClick}
            onRateMovieClick={handleRateMovieClick}
          />

          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-3 border-b border-[#D9D3C7]">
            <div>
              <h2 className="font-['Jost',sans-serif] font-bold text-xl sm:text-2xl uppercase tracking-[0.1em] text-[#141414]">
                Explore the Catalogue
              </h2>
              <p className="text-xs text-[#5E5A52] font-medium mt-1">
                Search titles or apply genre filters across all available films
              </p>
            </div>

            {/* Search Input Box */}
            <div className="w-full md:w-80 relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#5E5A52]">
                <Search className="w-4 h-4" />
              </div>
              <input
                type="text"
                id="catalogue-search-input"
                value={searchTerm}
                onChange={handleSearchChange}
                placeholder="Search by title..."
                className="w-full pl-9 pr-9 py-2 bg-white border border-[#D9D3C7] text-sm text-[#141414] placeholder-[#5E5A52]/60 font-['Jost',sans-serif] focus:outline-none focus:border-[#C8412B] focus:ring-1 focus:ring-[#C8412B] transition-colors"
              />
              {searchTerm && (
                <button
                  type="button"
                  onClick={clearSearch}
                  aria-label="Clear search"
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-[#5E5A52] hover:text-[#141414] cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>

          {/* Active Filter Chips */}
          {(activeSearch || selectedGenres.length > 0) && (
            <div className="flex flex-wrap items-center gap-2 text-xs font-['Jost',sans-serif]">
              <span className="text-[#5E5A52] uppercase tracking-wider font-semibold">Active filters:</span>
              {activeSearch && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-white border border-[#D9D3C7] text-[#141414] font-medium">
                  Title: "{activeSearch}"
                  <button
                    type="button"
                    onClick={clearSearch}
                    className="hover:text-[#C8412B] font-bold cursor-pointer"
                    aria-label="Remove search filter"
                  >
                    &times;
                  </button>
                </span>
              )}
              {selectedGenres.map((g) => (
                <span
                  key={g}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#141414] text-white uppercase tracking-wider font-semibold"
                >
                  {g}
                  <button
                    type="button"
                    onClick={() => toggleGenre(g)}
                    className="hover:text-[#C8412B] font-bold cursor-pointer ml-1"
                    aria-label={`Remove ${g} filter`}
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Catalogue Poster Grid */}
          <MovieGrid
            movies={catalogueMovies}
            loading={loadingCatalogue}
            error={catalogueError}
            onCardClick={handleCardClick}
            onRateMovieClick={handleRateMovieClick}
            isAuthenticated={isAuthenticated}
            skeletonCount={moviesPerPage}
            emptyAction={
              <button
                type="button"
                onClick={() => {
                  clearSearch();
                  clearAllGenres();
                }}
                className="px-5 py-2.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
              >
                Clear all filters
              </button>
            }
          />

          {/* Pagination */}
          {!loadingCatalogue && hasMoreCatalogue && catalogueMovies.length > 0 && (
            <div className="text-center pt-8">
              <button
                type="button"
                onClick={handleLoadMore}
                className="px-8 py-3 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
              >
                Load More Titles
              </button>
            </div>
          )}

          {loadingCatalogue && catalogueMovies.length > 0 && (
            <div className="text-center py-6 text-xs uppercase tracking-wider font-['Jost',sans-serif] text-[#5E5A52] font-semibold">
              Loading additional titles...
            </div>
          )}
        </section>
      </div>

      {/* Rating Modal */}
      <RatingModal
        movie={showRatingModalFor}
        show={Boolean(showRatingModalFor)}
        onClose={handleRatingModalClose}
        token={token}
      />
    </div>
  );
};

export default HomePage;
