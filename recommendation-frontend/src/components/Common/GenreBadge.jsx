import React from "react";

/**
 * Editorial genre badge / chip with clean borders and active coral states.
 */
const GenreBadge = ({
  genre,
  active = false,
  onClick,
  size = "sm",
  className = "",
}) => {
  const isClickable = Boolean(onClick);

  const sizeClasses = {
    xs: "px-2 py-0.5 text-[10px]",
    sm: "px-2.5 py-1 text-xs",
    md: "px-3.5 py-1.5 text-xs sm:text-sm",
  };

  const activeClasses = active
    ? "bg-[#C8412B] text-white border-[#C8412B] font-bold shadow-xs"
    : "bg-white text-[#141414] border-[#D9D3C7] hover:border-[#141414] font-medium";

  const Component = isClickable ? "button" : "span";

  return (
    <Component
      type={isClickable ? "button" : undefined}
      onClick={onClick}
      className={`inline-flex items-center uppercase tracking-wider font-['Jost',sans-serif] border transition-colors select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B] ${sizeClasses[size] || sizeClasses.sm} ${activeClasses} ${isClickable ? "cursor-pointer" : ""} ${className}`}
    >
      {genre}
    </Component>
  );
};

export default GenreBadge;
