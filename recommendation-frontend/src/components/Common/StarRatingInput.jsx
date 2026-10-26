import React, { useState } from "react";

const RATING_LABELS = {
  1: "Poor (1.0)",
  2: "Fair (2.0)",
  3: "Good (3.0)",
  4: "Very Good (4.0)",
  5: "Masterpiece (5.0)",
};

/**
 * Editorial StarRatingInput with accessible keyboard navigation and coral accent.
 */
const StarRatingInput = ({ rating, setRating, maxStars = 5 }) => {
  const [hoverRating, setHoverRating] = useState(0);

  const activeValue = hoverRating || rating || 0;

  const handleKeyDown = (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowUp") {
      e.preventDefault();
      setRating(Math.min(maxStars, (rating || 0) + 1));
    } else if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
      e.preventDefault();
      setRating(Math.max(1, (rating || 0) - 1));
    } else if (e.key >= "1" && e.key <= String(maxStars)) {
      e.preventDefault();
      setRating(parseInt(e.key, 10));
    }
  };

  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className="flex items-center gap-1.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B] p-1"
        tabIndex={0}
        role="radiogroup"
        aria-label="Movie rating from 1 to 5 stars"
        onKeyDown={handleKeyDown}
      >
        {Array.from({ length: maxStars }).map((_, index) => {
          const starValue = index + 1;
          const isFilled = activeValue >= starValue;
          return (
            <button
              type="button"
              key={starValue}
              role="radio"
              aria-checked={rating === starValue}
              aria-label={`${starValue} star${starValue > 1 ? "s" : ""}`}
              onClick={() => setRating(starValue)}
              onMouseEnter={() => setHoverRating(starValue)}
              onMouseLeave={() => setHoverRating(0)}
              className={`p-1 text-2xl transition-transform duration-100 cursor-pointer hover:scale-125 focus:outline-none ${
                isFilled ? "text-[#C8412B]" : "text-[#D9D3C7] hover:text-[#C8412B]/60"
              }`}
            >
              ★
            </button>
          );
        })}
      </div>
      <span className="text-xs font-['Jost',sans-serif] font-semibold uppercase tracking-wider text-[#5E5A52] min-h-[1.25rem]">
        {activeValue > 0 ? RATING_LABELS[activeValue] || `${activeValue}.0 / 5.0` : "Select a rating (1-5)"}
      </span>
    </div>
  );
};

export default StarRatingInput;
