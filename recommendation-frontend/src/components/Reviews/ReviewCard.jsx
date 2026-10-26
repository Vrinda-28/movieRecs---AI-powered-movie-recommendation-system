import React, { useState } from "react";
import RatingStars from "../Common/RatingStars";
import ReviewForm from "./ReviewForm";

/**
 * Editorial ReviewCard:
 * - Privacy protection: never leaks another user's email address ("Member" or "You").
 * - Localized date formatting.
 * - Comfortable typography (~70 characters max width).
 * - Edit/Delete permissions for owner/admin.
 */
const ReviewCard = ({
  review,
  currentUserId,
  currentUserEmail,
  isAdmin = false,
  onUpdate,
  onDelete,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(false);

  const isAuthor =
    (currentUserId && review.user_id === currentUserId) ||
    (currentUserEmail && review.user_email === currentUserEmail);
  const canDelete = isAuthor || isAdmin;

  const handleEditSubmit = async (newText) => {
    setLoading(true);
    try {
      await onUpdate(review.id, newText);
      setIsEditing(false);
    } finally {
      setLoading(false);
    }
  };

  const formattedDate = review.created_at
    ? new Date(review.created_at).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "Recently";

  // Strict privacy rule: Never display another user's email address
  const displayName = isAuthor ? "You" : "Member";

  return (
    <div className="p-5 sm:p-6 bg-white border border-[#D9D3C7] space-y-3.5 transition-shadow">
      {/* Header: User label & Date & Rating */}
      <div className="flex items-center justify-between border-b border-[#D9D3C7]/60 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-[#141414] text-[#FAF7F2] font-['Jost',sans-serif] font-bold text-xs flex items-center justify-center">
            {displayName[0]}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-['Jost',sans-serif] font-bold text-sm text-[#141414] uppercase tracking-wider">
                {displayName}
              </span>
              {isAuthor && (
                <span className="text-[10px] font-bold uppercase tracking-wider bg-[#C8412B] text-white px-1.5 py-0.5">
                  Author
                </span>
              )}
            </div>
            <span className="text-xs text-[#5E5A52] font-medium">{formattedDate}</span>
          </div>
        </div>

        {/* Rating if present in API */}
        {review.user_rating && (
          <RatingStars rating={review.user_rating} size="xs" showNumeric={true} theme="ink" />
        )}
      </div>

      {/* Body: Text or Edit Form with ~70 character reading width */}
      {isEditing ? (
        <ReviewForm
          initialText={review.text}
          isEditing={true}
          loading={loading}
          onSubmit={handleEditSubmit}
          onCancel={() => setIsEditing(false)}
        />
      ) : (
        <p className="text-sm text-[#141414] leading-relaxed max-w-[70ch] whitespace-pre-line font-['Jost',sans-serif]">
          {review.text}
        </p>
      )}

      {/* Footer: Actions for author or admin */}
      {!isEditing && (isAuthor || canDelete) && (
        <div className="flex items-center justify-end gap-4 pt-2 border-t border-[#D9D3C7]/40 text-xs">
          {isAuthor && (
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              className="text-[#141414] hover:text-[#C8412B] font-semibold uppercase tracking-wider transition-colors cursor-pointer"
            >
              Edit
            </button>
          )}
          {canDelete && (
            <button
              type="button"
              onClick={() => onDelete(review.id)}
              className="text-[#5E5A52] hover:text-[#C8412B] font-semibold uppercase tracking-wider transition-colors cursor-pointer"
            >
              Delete
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default ReviewCard;
