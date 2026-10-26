import React from "react";

const LoadingSpinner = ({ text = "Loading..." }) => {
  return (
    <div className="flex flex-col items-center justify-center p-8 sm:p-12 text-[#141414]">
      <div className="w-8 h-8 rounded-full border-2 border-[#D9D3C7] border-t-[#C8412B] animate-spin mb-3"></div>
      <p className="font-['Jost',sans-serif] text-xs font-semibold uppercase tracking-widest text-[#5E5A52]">
        {text}
      </p>
    </div>
  );
};

export default LoadingSpinner;
