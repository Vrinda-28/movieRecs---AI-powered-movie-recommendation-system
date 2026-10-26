import React, { useState, useEffect, useRef, useCallback } from "react";
import { Sparkles, X, RotateCcw, AlertCircle, Info, ChevronRight } from "lucide-react";
import ApiService from "../../services/ApiService";
import MovieCard from "./MovieCard";
import LoadingSpinner from "./LoadingSpinner";

const EXAMPLE_PROMPTS = [
  "Mind-bending sci-fi with an emotional story, similar to Interstellar, no horror, fairly recent",
  "90s fast-paced crime thrillers with dark humor",
  "Classic witty romantic comedy from the 1940s or 1950s",
];

const AiPromptPanel = ({
  isAuthenticated,
  token,
  navigateTo,
  onCardClick,
  onRateMovieClick,
}) => {
  const [aiEnabled, setAiEnabled] = useState(null); // null = loading check, true/false
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [resultsData, setResultsData] = useState(null);
  const abortControllerRef = useRef(null);

  // Check AI feature status on mount
  useEffect(() => {
    const controller = new AbortController();
    ApiService.getAiStatus(controller.signal)
      .then((res) => {
        setAiEnabled(Boolean(res?.enabled));
      })
      .catch(() => {
        // Quiet fallback if status check fails (e.g. backend down or error)
        setAiEnabled(false);
      });

    return () => controller.abort();
  }, []);

  // Cleanup in-flight requests on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const handleDiscover = useCallback(
    async (textToSubmit) => {
      const query = (textToSubmit !== undefined ? textToSubmit : prompt).trim();
      if (!query || query.length < 3 || query.length > 500) return;

      if (!isAuthenticated || !token) {
        navigateTo("login");
        return;
      }

      // Abort previous in-flight request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      setLoading(true);
      setError(null);

      try {
        const data = await ApiService.aiDiscover(
          query,
          token,
          abortControllerRef.current.signal,
        );
        setResultsData(data);
      } catch (err) {
        if (err.name === "AbortError") return;

        let friendlyMsg = "Failed to discover movies. Please try again.";
        const detailCode = err.detail || "";

        if (detailCode === "ai_not_configured" || err.status === 503) {
          friendlyMsg = "AI movie discovery is currently not configured on this server.";
        } else if (
          detailCode === "ai_quota_exceeded" ||
          detailCode === "ai_rate_limited" ||
          err.status === 429
        ) {
          friendlyMsg =
            "AI request limit reached. Please wait a moment before trying again.";
        } else if (detailCode === "ai_timeout" || err.status === 504) {
          friendlyMsg =
            "The request timed out. The AI model took too long to respond. Please retry.";
        } else if (detailCode === "ai_bad_response" || err.status === 502) {
          friendlyMsg =
            "The AI service could not interpret your description. Try rephrasing with different keywords.";
        } else if (detailCode === "ai_auth_failed") {
          friendlyMsg =
            "AI service authentication failed. Please contact the administrator.";
        } else if (err.status === 401) {
          friendlyMsg = "Your session expired. Please log in again.";
          navigateTo("login");
        } else if (err.message) {
          friendlyMsg = err.message;
        }

        setError({ message: friendlyMsg, query });
      } finally {
        setLoading(false);
      }
    },
    [prompt, isAuthenticated, token, navigateTo],
  );

  const handleClear = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setResultsData(null);
    setError(null);
    setPrompt("");
  };

  const handleChipClick = (example) => {
    setPrompt(example);
    handleDiscover(example);
  };

  // If status is checked and disabled, display muted notice without breaking layout
  if (aiEnabled === false) {
    return (
      <div className="p-4 bg-white border border-[#D9D3C7] text-xs font-['Jost',sans-serif] text-[#5E5A52] flex items-center justify-between">
        <span>AI natural-language discovery is currently not configured.</span>
      </div>
    );
  }

  return (
    <div className="space-y-6" aria-label="AI movie discovery section">
      {/* Search Input Box */}
      <div className="p-5 sm:p-6 bg-white border border-[#D9D3C7] shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-[#D9D3C7]">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-[#C8412B]" />
            <h3 className="font-['Jost',sans-serif] font-bold text-base sm:text-lg uppercase tracking-[0.08em] text-[#141414]">
              Describe What You Want to Watch
            </h3>
          </div>
          {resultsData && (
            <button
              type="button"
              onClick={handleClear}
              className="text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#C8412B] hover:underline self-end sm:self-auto cursor-pointer"
            >
              Clear AI Results
            </button>
          )}
        </div>

        <p className="text-xs text-[#5E5A52] font-['Jost',sans-serif] leading-relaxed">
          Tell us about the mood, themes, reference films, or era you are in the mood for.
          Our grounded AI maps your description strictly against real films in our catalogue.
        </p>

        {/* Input Textarea & Counter */}
        <div className="space-y-1.5">
          <label htmlFor="ai-prompt-input" className="sr-only">
            Describe what you want to watch
          </label>
          <div className="relative">
            <textarea
              id="ai-prompt-input"
              rows={3}
              value={prompt}
              disabled={loading}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleDiscover();
                }
              }}
              placeholder="e.g. Mind-bending sci-fi with an emotional story, similar to Interstellar, no horror, fairly recent"
              maxLength={500}
              className="w-full p-3.5 bg-[#FAF7F2] border border-[#D9D3C7] text-sm text-[#141414] placeholder-[#5E5A52]/60 font-['Jost',sans-serif] focus:outline-none focus:border-[#C8412B] focus:ring-1 focus:ring-[#C8412B] transition-colors resize-none disabled:opacity-50"
            />
          </div>

          <div className="flex items-center justify-between text-[11px] font-['Jost',sans-serif] text-[#5E5A52]">
            <span>Press Enter to discover, or click Search</span>
            <span className={prompt.length > 480 ? "text-[#C8412B] font-bold" : ""}>
              {prompt.length}/500
            </span>
          </div>
        </div>

        {/* Example Prompt Chips */}
        <div className="space-y-1.5 pt-1">
          <span className="text-[11px] font-['Jost',sans-serif] font-semibold uppercase tracking-wider text-[#5E5A52]">
            Try an example prompt:
          </span>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_PROMPTS.map((ex, idx) => (
              <button
                key={idx}
                type="button"
                disabled={loading}
                onClick={() => handleChipClick(ex)}
                className="text-left text-xs font-['Jost',sans-serif] px-3 py-1.5 bg-[#FAF7F2] hover:bg-[#EFEAE1] border border-[#D9D3C7] text-[#141414] transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
              >
                <ChevronRight className="w-3 h-3 text-[#C8412B] shrink-0" />
                <span className="line-clamp-1">{ex}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-2">
          {!isAuthenticated ? (
            <div className="flex items-center justify-between w-full p-3 bg-[#FAF7F2] border border-[#D9D3C7]">
              <span className="text-xs font-['Jost',sans-serif] text-[#5E5A52]">
                Log in to search the catalogue with AI discovery
              </span>
              <button
                type="button"
                onClick={() => navigateTo("login")}
                className="px-4 py-1.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
              >
                Log In
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3 w-full sm:w-auto ml-auto">
              {resultsData && (
                <button
                  type="button"
                  onClick={handleClear}
                  disabled={loading}
                  className="px-4 py-2 border border-[#D9D3C7] hover:border-[#141414] text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#141414] transition-colors cursor-pointer disabled:opacity-50"
                >
                  Clear
                </button>
              )}
              <button
                type="button"
                onClick={() => handleDiscover()}
                disabled={loading || prompt.trim().length < 3}
                className="flex-1 sm:flex-initial px-6 py-2.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <Sparkles className="w-3.5 h-3.5" />
                {loading ? "Discovering..." : "Discover Movies"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="p-8 bg-white border border-[#D9D3C7] text-center" aria-live="polite">
          <LoadingSpinner text="Analyzing preferences & matching catalogue titles..." />
        </div>
      )}

      {/* Error State with Retry */}
      {error && !loading && (
        <div
          role="alert"
          className="p-5 bg-white border border-[#C8412B] text-left space-y-3"
          aria-live="polite"
        >
          <div className="flex items-start gap-2.5 text-[#C8412B]">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h4 className="font-['Jost',sans-serif] font-bold text-xs uppercase tracking-wider">
                Discovery Request Issue
              </h4>
              <p className="font-['Jost',sans-serif] text-xs text-[#141414] leading-relaxed">
                {error.message}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleDiscover(error.query)}
            className="px-4 py-1.5 bg-[#C8412B] hover:bg-[#A8321F] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider transition-colors cursor-pointer inline-flex items-center gap-1.5"
          >
            <RotateCcw className="w-3 h-3" />
            Retry
          </button>
        </div>
      )}

      {/* Results Section */}
      {resultsData && !loading && (
        <section
          aria-label="AI Discovery Results"
          className="space-y-5"
          aria-live="polite"
        >
          {/* Interpretation Details Card */}
          <div className="p-4 sm:p-5 bg-white border border-[#D9D3C7] space-y-3 text-xs font-['Jost',sans-serif]">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#D9D3C7] pb-2">
              <span className="font-bold uppercase tracking-wider text-[#141414] flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-[#C8412B]" />
                Interpreted Preferences
              </span>
              <button
                type="button"
                onClick={handleClear}
                className="text-[#C8412B] hover:underline font-semibold cursor-pointer"
              >
                Close AI View
              </button>
            </div>

            {/* Structured Criteria Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
              {/* Included / Excluded Genres */}
              <div className="space-y-1.5">
                {resultsData.interpreted?.include_genres?.length > 0 && (
                  <div>
                    <span className="text-[#5E5A52] font-semibold uppercase tracking-wider mr-2">
                      Target Genres:
                    </span>
                    <span className="text-[#141414] font-medium">
                      {resultsData.interpreted.include_genres.join(", ")}
                    </span>
                  </div>
                )}
                {resultsData.interpreted?.exclude_genres?.length > 0 && (
                  <div>
                    <span className="text-[#C8412B] font-semibold uppercase tracking-wider mr-2">
                      Excluded Genres:
                    </span>
                    <span className="text-[#141414] line-through">
                      {resultsData.interpreted.exclude_genres.join(", ")}
                    </span>
                  </div>
                )}
              </div>

              {/* Year & Reference Titles */}
              <div className="space-y-1.5">
                {(resultsData.interpreted?.year_min || resultsData.interpreted?.year_max) && (
                  <div>
                    <span className="text-[#5E5A52] font-semibold uppercase tracking-wider mr-2">
                      Release Period:
                    </span>
                    <span className="text-[#141414] font-medium">
                      {resultsData.interpreted.year_min || "Any"} – {resultsData.interpreted.year_max || "Present"}
                    </span>
                  </div>
                )}
                {resultsData.interpreted?.reference_titles?.length > 0 && (
                  <div>
                    <span className="text-[#5E5A52] font-semibold uppercase tracking-wider mr-2">
                      Referenced Titles:
                    </span>
                    <span className="text-[#141414] font-medium">
                      {resultsData.interpreted.reference_titles.join(", ")}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Unresolved References Notice */}
            {resultsData.unresolved_references?.length > 0 && (
              <div className="p-2.5 bg-[#FAF7F2] border border-[#D9D3C7] text-[#5E5A52] flex items-start gap-2">
                <Info className="w-3.5 h-3.5 text-[#C8412B] shrink-0 mt-0.5" />
                <span className="text-xs leading-relaxed">
                  <strong>Catalogue Note:</strong> "{resultsData.unresolved_references.join(", ")}" is not present in this catalogue archive, but its genres and thematic cues were used to find matching catalogue titles below.
                </span>
              </div>
            )}

            {/* Unverified Attributes Notice */}
            {resultsData.unverified?.length > 0 && (
              <div className="pt-2 border-t border-[#D9D3C7] text-[#5E5A52] italic text-[11px] leading-relaxed">
                Couldn't verify from catalogue data: {resultsData.unverified.join(" • ")}
              </div>
            )}

            {/* Relaxed Constraints Notice */}
            {resultsData.relaxed?.length > 0 && (
              <div className="p-2.5 bg-[#FAF7F2] border border-[#D9D3C7] text-[#141414] font-medium">
                Note: {resultsData.relaxed.join(", ")} to present closest catalogue matches.
              </div>
            )}
          </div>

          {/* Empty Results State */}
          {resultsData.results.length === 0 ? (
            <div className="p-10 bg-white border border-[#D9D3C7] text-center space-y-3">
              <h4 className="font-['Jost',sans-serif] font-bold text-base uppercase tracking-wider text-[#141414]">
                No Matching Catalogue Titles
              </h4>
              <p className="font-['Jost',sans-serif] text-xs text-[#5E5A52] max-w-md mx-auto">
                No catalogue movies matched your exact constraints. Try fewer genres or wider year ranges.
              </p>
              <button
                type="button"
                onClick={handleClear}
                className="px-5 py-2 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer"
              >
                Return to Full Catalogue
              </button>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between pb-3">
                <h4 className="font-['Jost',sans-serif] font-bold text-sm uppercase tracking-wider text-[#141414]">
                  Discovered Titles ({resultsData.results.length})
                </h4>
                <span className="text-xs font-['Jost',sans-serif] text-[#5E5A52]">
                  Ranked by catalogue relevance
                </span>
              </div>

              {/* Responsive MovieCard Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 sm:gap-6">
                {resultsData.results.map((movie, idx) => (
                  <div key={`${movie.movie_id}-${idx}`} className="flex flex-col">
                    <MovieCard
                      movie={{
                        ...movie,
                        id: movie.movie_id,
                      }}
                      rank={idx + 1}
                      onCardClick={onCardClick}
                      onRateMovieClick={onRateMovieClick}
                      isAuthenticated={isAuthenticated}
                      priority={idx < 4}
                    />

                    {/* Explanatory Reasons Under Card */}
                    {movie.reasons && movie.reasons.length > 0 && (
                      <div className="mt-2 px-1 space-y-0.5">
                        {movie.reasons.map((reason, rIdx) => (
                          <p
                            key={rIdx}
                            className="text-[11px] leading-tight text-[#5E5A52] italic font-['Jost',sans-serif]"
                          >
                            • {reason}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
};

export default AiPromptPanel;
