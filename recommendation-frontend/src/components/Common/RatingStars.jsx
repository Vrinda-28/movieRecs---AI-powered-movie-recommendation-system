import React from "react";
import StarIcon from "../Icons/StarIcon";

/**
 * Editorial star rating display with half-star precision, accessible label,
 * and support for ink or white star palettes.
 */
const RatingStars = ({
  rating = 0,
  numRatings = null,
  size = "sm",
  showNumeric = true,
  theme = "ink", // "ink" (black #141414) or "white" (#FFFFFF) or "amber"
  className = "",
}) => {
  const numericRating = typeof rating === "number" ? rating : parseFloat(rating) || 0;
  const clampedRating = Math.max(0, Math.min(5, numericRating));
  const hasNoRatings = numRatings === 0;

  const sizeClasses = {
    xs: "w-3 h-3",
    sm: "w-3.5 h-3.5",
    md: "w-4 h-4",
    lg: "w-5 h-5",
  };

  const starSize = sizeClasses[size] || sizeClasses.sm;

  const colorStyles = {
    ink: {
      starFilled: "text-[#141414]",
      starEmpty: "text-[#D9D3C7]",
      text: "text-[#141414]",
      subtext: "text-[#5E5A52]",
    },
    white: {
      starFilled: "text-white",
      starEmpty: "text-white/40",
      text: "text-white",
      subtext: "text-white/80",
    },
    amber: {
      starFilled: "text-amber-500",
      starEmpty: "text-slate-300",
      text: "text-[#141414]",
      subtext: "text-[#5E5A52]",
    },
  };

  const colors = colorStyles[theme] || colorStyles.ink;

  if (hasNoRatings) {
    return (
      <div className={`inline-flex items-center gap-1.5 ${className}`} aria-label="Not yet rated">
        <span className={`text-xs font-medium uppercase tracking-wider ${colors.subtext}`}>
          Not yet rated
        </span>
      </div>
    );
  }

  const ariaText = numRatings
    ? `Average ${clampedRating.toFixed(1)} out of 5 from ${numRatings.toLocaleString()} ratings`
    : `Rating ${clampedRating.toFixed(1)} out of 5`;

  return (
    <div
      className={`inline-flex items-center gap-1.5 ${className}`}
      aria-label={ariaText}
      role="img"
    >
      <div className="flex items-center">
        {[1, 2, 3, 4, 5].map((starIdx) => {
          const isFilled = clampedRating >= starIdx;
          const isHalf = !isFilled && clampedRating >= starIdx - 0.5;
          return (
            <StarIcon
              key={starIdx}
              filled={isFilled}
              halfFilled={isHalf}
              className={`${starSize} ${isFilled || isHalf ? colors.starFilled : colors.starEmpty}`}
            />
          );
        })}
      </div>

      {showNumeric && (
        <span className={`font-semibold text-xs tabular-nums ${colors.text}`}>
          {clampedRating > 0 ? clampedRating.toFixed(1) : "—"}
        </span>
      )}

      {numRatings !== null && numRatings !== undefined && numRatings > 0 && (
        <span className={`text-[11px] tabular-nums ${colors.subtext}`}>
          ({numRatings.toLocaleString()})
        </span>
      )}
    </div>
  );
};

export default RatingStars;
