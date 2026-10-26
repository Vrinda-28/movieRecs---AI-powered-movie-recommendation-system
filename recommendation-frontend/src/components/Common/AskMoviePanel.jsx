import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  MessageSquare,
  Sparkles,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  AlertCircle,
  Film,
  Send,
  HelpCircle,
} from "lucide-react";
import ApiService from "../../services/ApiService";
import MovieCard from "./MovieCard";
import LoadingSpinner from "./LoadingSpinner";

const SUGGESTED_QUESTIONS = [
  "What is this movie about?",
  "Recommend three similar movies from our catalogue",
  "Does this movie contain horror or graphic violence?",
  "Explain why this movie matches my preferences",
];

const AskMoviePanel = ({
  movieId,
  movieTitle,
  isAuthenticated,
  token,
  navigateTo,
  onMovieClick,
}) => {
  const [aiEnabled, setAiEnabled] = useState(null);
  const [isOpen, setIsOpen] = useState(true);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([]); // Array of { role: 'user'|'assistant', data?: AskResponse, text: str }
  const abortControllerRef = useRef(null);

  // Check AI feature status on mount
  useEffect(() => {
    const controller = new AbortController();
    ApiService.getAiStatus(controller.signal)
      .then((res) => {
        setAiEnabled(Boolean(res?.enabled));
      })
      .catch(() => {
        setAiEnabled(false);
      });

    return () => controller.abort();
  }, []);

  // Reset conversation and abort when movieId changes
  useEffect(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setMessages([]);
    setError(null);
    setQuestion("");
  }, [movieId]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const handleAsk = useCallback(
    async (textToSubmit) => {
      const q = (textToSubmit !== undefined ? textToSubmit : question).trim();
      if (!q || q.length < 3 || q.length > 500) return;

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

      // Build session history for backend (max 6 previous items)
      const historyPayload = messages.slice(-6).map((m) => ({
        role: m.role,
        text: m.text.slice(0, 500),
      }));

      // Optimistically add user turn to UI
      const userMessage = { role: "user", text: q };
      setMessages((prev) => [...prev, userMessage]);
      setQuestion("");

      try {
        const response = await ApiService.aiAsk(
          {
            question: q,
            movieId: movieId ? parseInt(movieId, 10) : null,
            history: historyPayload,
          },
          token,
          abortControllerRef.current.signal,
        );

        const assistantMessage = {
          role: "assistant",
          text: response.answer,
          data: response,
        };
        setMessages((prev) => [...prev, assistantMessage]);
      } catch (err) {
        if (err.name === "AbortError") return;

        let friendlyMsg = "Failed to answer question. Please try again.";
        const detailCode = err.detail || "";

        if (detailCode === "ai_not_configured" || err.status === 503) {
          friendlyMsg = "AI movie Q&A is currently not configured on this server.";
        } else if (
          detailCode === "ai_quota_exceeded" ||
          detailCode === "ai_rate_limited" ||
          err.status === 429
        ) {
          friendlyMsg =
            "AI request limit reached. Please wait a moment before asking another question.";
        } else if (detailCode === "ai_timeout" || err.status === 504) {
          friendlyMsg =
            "The request timed out. The AI model took too long to respond. Please retry.";
        } else if (detailCode === "ai_bad_response" || err.status === 502) {
          friendlyMsg =
            "Could not process the response from the AI model. Please try asking in a different way.";
        } else if (detailCode === "ai_auth_failed") {
          friendlyMsg = "AI authentication failed. Please contact the administrator.";
        } else if (err.status === 401) {
          friendlyMsg = "Your session expired. Please log in again.";
          navigateTo("login");
        } else if (err.message) {
          friendlyMsg = err.message;
        }

        setError({ message: friendlyMsg, question: q });
      } finally {
        setLoading(false);
      }
    },
    [question, isAuthenticated, token, messages, movieId, navigateTo],
  );

  const handleChipClick = (suggested) => {
    setQuestion(suggested);
    handleAsk(suggested);
  };

  // If status is checked and disabled, show quiet notice
  if (aiEnabled === false) {
    return (
      <div className="p-4 bg-white border border-[#D9D3C7] text-xs font-['Jost',sans-serif] text-[#5E5A52]">
        AI grounded Q&A is currently not configured.
      </div>
    );
  }

  return (
    <section
      aria-label="Ask about this movie"
      className="p-5 sm:p-6 bg-white border border-[#D9D3C7] shadow-sm space-y-4"
    >
      {/* Header with Collapsible Toggle */}
      <div className="flex items-center justify-between pb-2 border-b border-[#D9D3C7]">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-[#C8412B]" />
          <h3 className="font-['Jost',sans-serif] font-bold text-sm sm:text-base uppercase tracking-widest text-[#141414]">
            Ask About This Movie
          </h3>
        </div>
        <div className="flex items-center gap-3">
          {messages.length > 0 && (
            <button
              type="button"
              onClick={() => setMessages([])}
              className="text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider text-[#C8412B] hover:underline cursor-pointer"
            >
              Reset Chat
            </button>
          )}
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            className="p-1 hover:bg-[#FAF7F2] text-[#5E5A52] hover:text-[#141414] transition-colors cursor-pointer"
            aria-label={isOpen ? "Collapse panel" : "Expand panel"}
          >
            {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {isOpen && (
        <div className="space-y-4 pt-1">
          <p className="text-xs text-[#5E5A52] font-['Jost',sans-serif] leading-relaxed">
            Have questions about {movieTitle || "this film"}? Ask below.
            Answers are strictly grounded in verified catalogue data, separating facts from interpretations.
          </p>

          {/* Suggested Question Chips */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-['Jost',sans-serif] font-semibold uppercase tracking-wider text-[#5E5A52]">
              Suggested questions:
            </span>
            <div className="flex flex-wrap gap-2">
              {SUGGESTED_QUESTIONS.map((sq, idx) => (
                <button
                  key={idx}
                  type="button"
                  disabled={loading}
                  onClick={() => handleChipClick(sq)}
                  className="text-left text-xs font-['Jost',sans-serif] px-3 py-1.5 bg-[#FAF7F2] hover:bg-[#EFEAE1] border border-[#D9D3C7] text-[#141414] transition-colors cursor-pointer disabled:opacity-50"
                >
                  {sq}
                </button>
              ))}
            </div>
          </div>

          {/* Conversation History List */}
          {messages.length > 0 && (
            <div
              className="space-y-4 pt-2 border-t border-[#D9D3C7]"
              aria-live="polite"
            >
              {messages.map((msg, idx) => (
                <div key={idx} className="space-y-2">
                  {msg.role === "user" ? (
                    <div className="flex items-start gap-2 max-w-xl ml-auto justify-end">
                      <div className="p-3 bg-[#141414] text-white text-xs font-['Jost',sans-serif] leading-relaxed rounded-none border border-black">
                        {msg.text}
                      </div>
                    </div>
                  ) : (
                    <div className="p-4 bg-[#FAF7F2] border border-[#D9D3C7] space-y-3 text-xs font-['Jost',sans-serif]">
                      {/* Main Grounded Answer Text */}
                      <p className="text-[#141414] leading-relaxed whitespace-pre-wrap font-medium">
                        {msg.text}
                      </p>

                      {/* Labelled Sections: Catalogue Facts, Interpretation, Cannot Verify */}
                      {msg.data && (
                        <div className="space-y-2 pt-2 border-t border-[#D9D3C7]">
                          {/* From the Catalogue */}
                          {msg.data.catalogue_facts?.length > 0 && (
                            <div className="space-y-1">
                              <span className="block font-bold uppercase tracking-wider text-[#141414] text-[11px]">
                                From the Catalogue:
                              </span>
                              <ul className="list-disc list-inside space-y-0.5 text-[#5E5A52]">
                                {msg.data.catalogue_facts.map((fact, fIdx) => (
                                  <li key={fIdx}>{fact}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Interpretation */}
                          {msg.data.interpretation?.length > 0 && (
                            <div className="space-y-1">
                              <span className="block font-bold uppercase tracking-wider text-[#141414] text-[11px]">
                                Interpretation:
                              </span>
                              <ul className="list-disc list-inside space-y-0.5 text-[#5E5A52]">
                                {msg.data.interpretation.map((item, iIdx) => (
                                  <li key={iIdx}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Can't Be Verified */}
                          {msg.data.cannot_verify?.length > 0 && (
                            <div className="space-y-1">
                              <span className="block font-bold uppercase tracking-wider text-[#C8412B] text-[11px]">
                                Can't Be Verified from Catalogue:
                              </span>
                              <ul className="list-disc list-inside space-y-0.5 text-[#5E5A52] italic">
                                {msg.data.cannot_verify.map((item, cIdx) => (
                                  <li key={cIdx}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Recommended Catalogue Movies Grid */}
                          {msg.data.movies?.length > 0 && (
                            <div className="space-y-2 pt-2 border-t border-[#D9D3C7]">
                              <span className="block font-bold uppercase tracking-wider text-[#141414] text-[11px] flex items-center gap-1.5">
                                <Film className="w-3.5 h-3.5 text-[#C8412B]" />
                                Referenced Catalogue Movies:
                              </span>
                              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                                {msg.data.movies.map((recMovie) => (
                                  <div
                                    key={recMovie.movie_id}
                                    onClick={() => onMovieClick && onMovieClick(recMovie.movie_id)}
                                    className="cursor-pointer"
                                  >
                                    <MovieCard
                                      movie={{
                                        ...recMovie,
                                        id: recMovie.movie_id,
                                      }}
                                      onCardClick={onMovieClick}
                                      isAuthenticated={isAuthenticated}
                                    />
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Loading Indicator */}
          {loading && (
            <div className="p-4 bg-[#FAF7F2] border border-[#D9D3C7] text-center" aria-live="polite">
              <LoadingSpinner text="Checking catalogue facts and preparing answer..." />
            </div>
          )}

          {/* Error Message with Retry */}
          {error && !loading && (
            <div
              role="alert"
              className="p-4 bg-white border border-[#C8412B] space-y-2 text-left"
              aria-live="polite"
            >
              <div className="flex items-start gap-2 text-[#C8412B]">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <p className="font-['Jost',sans-serif] text-xs text-[#141414] leading-relaxed">
                  {error.message}
                </p>
              </div>
              <button
                type="button"
                onClick={() => handleAsk(error.question)}
                className="px-3.5 py-1 bg-[#C8412B] hover:bg-[#A8321F] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider transition-colors cursor-pointer inline-flex items-center gap-1.5"
              >
                <RotateCcw className="w-3 h-3" />
                Retry
              </button>
            </div>
          )}

          {/* Input Box and Submit */}
          {!isAuthenticated ? (
            <div className="flex items-center justify-between p-3.5 bg-[#FAF7F2] border border-[#D9D3C7]">
              <span className="text-xs font-['Jost',sans-serif] text-[#5E5A52]">
                Log in to ask questions about this film
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
            <div className="space-y-1.5 pt-1">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={question}
                  disabled={loading}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAsk();
                    }
                  }}
                  placeholder="Ask a question about this movie (e.g. recommend similar titles)..."
                  maxLength={500}
                  className="flex-1 px-3.5 py-2.5 bg-[#FAF7F2] border border-[#D9D3C7] text-xs text-[#141414] placeholder-[#5E5A52]/60 font-['Jost',sans-serif] focus:outline-none focus:border-[#C8412B] focus:ring-1 focus:ring-[#C8412B] transition-colors disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => handleAsk()}
                  disabled={loading || question.trim().length < 3}
                  className="px-5 py-2.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1.5 shrink-0"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">{loading ? "Asking..." : "Ask"}</span>
                </button>
              </div>

              <div className="flex items-center justify-between text-[11px] font-['Jost',sans-serif] text-[#5E5A52]">
                <span>Answers are strictly based on verified catalogue records</span>
                <span className={question.length > 480 ? "text-[#C8412B] font-bold" : ""}>
                  {question.length}/500
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
};

export default AskMoviePanel;
