import React, { useState } from "react";

/**
 * Editorial ReviewForm with character counter and clear validation.
 */
const ReviewForm = ({
  onSubmit,
  onCancel,
  initialText = "",
  isEditing = false,
  loading = false,
}) => {
  const [text, setText] = useState(initialText);
  const [error, setError] = useState("");

  const maxChars = 2000;
  const remaining = maxChars - text.length;

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) {
      setError("Please write some thoughts before submitting.");
      return;
    }
    if (trimmed.length > maxChars) {
      setError(`Review cannot exceed ${maxChars} characters.`);
      return;
    }
    setError("");
    onSubmit(trimmed);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="relative">
        <textarea
          rows={4}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (error) setError("");
          }}
          placeholder="Share your perspective on the film's narrative, direction, performances, or score..."
          maxLength={maxChars}
          className="w-full p-4 bg-white border border-[#D9D3C7] text-[#141414] placeholder-[#5E5A52]/60 text-sm font-['Jost',sans-serif] focus:outline-none focus:border-[#C8412B] focus:ring-1 focus:ring-[#C8412B] transition-colors resize-y min-h-[110px]"
        />
        <div className="flex items-center justify-between mt-1 text-xs text-[#5E5A52]">
          <span>{error && <span className="text-[#C8412B] font-semibold">{error}</span>}</span>
          <span className="tabular-nums">
            {remaining} characters left
          </span>
        </div>
      </div>

      <div className="flex items-center justify-end gap-3">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 bg-transparent hover:bg-[#EFEAE1] text-[#141414] text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider border border-[#D9D3C7] transition-colors cursor-pointer"
          >
            Cancel
          </button>
        )}
        <button
          type="submit"
          disabled={loading || !text.trim()}
          className="px-6 py-2.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
        >
          {loading ? "Submitting..." : isEditing ? "Save Changes" : "Post Review"}
        </button>
      </div>
    </form>
  );
};

export default ReviewForm;
