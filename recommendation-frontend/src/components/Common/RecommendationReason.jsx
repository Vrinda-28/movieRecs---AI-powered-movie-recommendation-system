import React from "react";

/**
 * RecommendationReason Component
 * Renders an honest, mathematically supported explanation badge for recommended items.
 *
 * Supported reason_types:
 * - "embedding_neighbor": "Because you rated <Movie> highly" (Cosine similarity over candidate embeddings)
 * - "genre_overlap": "Shares genres (X, Y) with movies you rated highly"
 * - "recent_activity": "Based on your recent ratings"
 * - "popularity": "Popular with other users"
 */
const RecommendationReason = ({ reason, reasonType, reasonText, className = "" }) => {
  const type = reason?.reason_type || reasonType;
  const text = reason?.reason_text || reasonText;

  if (!type && !text) return null;

  // Visual style mappings by explanation method
  const configMap = {
    embedding_neighbor: {
      bg: "bg-indigo-950/80 border-indigo-500/40 text-indigo-200 hover:bg-indigo-900/90",
      dot: "bg-indigo-400",
      icon: (
        <svg className="w-3 h-3 text-indigo-300 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
        </svg>
      ),
      label: "Embedding Match",
    },
    genre_overlap: {
      bg: "bg-emerald-950/80 border-emerald-500/40 text-emerald-200 hover:bg-emerald-900/90",
      dot: "bg-emerald-400",
      icon: (
        <svg className="w-3 h-3 text-emerald-300 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
        </svg>
      ),
      label: "Shared Genre",
    },
    recent_activity: {
      bg: "bg-sky-950/80 border-sky-500/40 text-sky-200 hover:bg-sky-900/90",
      dot: "bg-sky-400",
      icon: (
        <svg className="w-3 h-3 text-sky-300 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      label: "Recent Activity",
    },
    popularity: {
      bg: "bg-amber-950/80 border-amber-500/40 text-amber-200 hover:bg-amber-900/90",
      dot: "bg-amber-400",
      icon: (
        <svg className="w-3 h-3 text-amber-300 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
      ),
      label: "Popular Baseline",
    },
  };

  const styleConfig = configMap[type] || configMap.recent_activity;

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border text-[11px] font-medium transition-all backdrop-blur-sm shadow-sm leading-tight ${styleConfig.bg} ${className}`}
      title={text || styleConfig.label}
    >
      {styleConfig.icon}
      <span className="truncate max-w-[200px]">{text || styleConfig.label}</span>
      {reason?.score !== null && reason?.score !== undefined && (
        <span className="text-[10px] font-mono font-semibold opacity-75 ml-0.5">
          ({(reason.score * 100).toFixed(0)}% sim)
        </span>
      )}
    </div>
  );
};

export default RecommendationReason;
