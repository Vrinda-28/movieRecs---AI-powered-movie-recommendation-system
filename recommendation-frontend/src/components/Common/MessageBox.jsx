import React from "react";

const MessageBox = ({ message, type, onDismiss }) => {
  if (!message) return null;

  const baseClasses =
    "fixed top-5 right-5 p-4 z-[100] text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider shadow-lg flex items-center border";
  const typeClasses =
    type === "error"
      ? "bg-[#C8412B] text-white border-[#A8321F]"
      : type === "success"
      ? "bg-[#141414] text-white border-black"
      : "bg-[#FAF7F2] text-[#141414] border-[#D9D3C7]";

  return (
    <div className={`${baseClasses} ${typeClasses}`} role="alert">
      <span className="flex-grow mr-4">{message}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="text-lg font-bold hover:opacity-80 focus:outline-none cursor-pointer"
          aria-label="Dismiss notification"
        >
          &times;
        </button>
      )}
    </div>
  );
};

export default MessageBox;
