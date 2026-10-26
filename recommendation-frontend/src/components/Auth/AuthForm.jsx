import React, { useState } from "react";
import { useAppContext } from "../../contexts/AppContext";

/**
 * Editorial AuthForm styled with warm paper and ink tokens.
 */
const AuthForm = ({ isLogin, onSubmit }) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { navigateTo } = useAppContext();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onSubmit({ username: email, password });
    } catch (err) {
      setError(
        err.data?.detail ||
          err.message ||
          (isLogin ? "Login failed." : "Registration failed."),
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="py-16 sm:py-24 flex items-center justify-center px-4">
      <div className="bg-white border border-[#D9D3C7] p-8 sm:p-10 shadow-lg w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <span className="font-['Jost',sans-serif] font-black text-2xl tracking-[0.14em] uppercase text-[#141414]">
            MOVIERECS
          </span>
          <h2 className="font-['Jost',sans-serif] font-bold text-lg uppercase tracking-wider text-[#141414]">
            {isLogin ? "Member Sign In" : "Create Account"}
          </h2>
          <p className="text-xs text-[#5E5A52] font-['Jost',sans-serif]">
            {isLogin
              ? "Access your personalized sequential recommendations"
              : "Register to begin tracking ratings and discoveries"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="email"
              className="block font-['Jost',sans-serif] text-xs font-bold uppercase tracking-wider text-[#5E5A52] mb-1.5"
            >
              Email Address
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
              className="w-full p-3 bg-white border border-[#D9D3C7] text-sm text-[#141414] placeholder-[#5E5A52]/50 font-['Jost',sans-serif] focus:outline-none focus:border-[#C8412B] focus:ring-1 focus:ring-[#C8412B] transition-colors"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block font-['Jost',sans-serif] text-xs font-bold uppercase tracking-wider text-[#5E5A52] mb-1.5"
            >
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete={isLogin ? "current-password" : "new-password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full p-3 bg-white border border-[#D9D3C7] text-sm text-[#141414] placeholder-[#5E5A52]/50 font-['Jost',sans-serif] focus:outline-none focus:border-[#C8412B] focus:ring-1 focus:ring-[#C8412B] transition-colors"
            />
          </div>

          {error && (
            <p className="text-xs font-semibold text-[#C8412B] bg-[#FAF7F2] border border-[#C8412B]/40 p-2.5">
              {error}
            </p>
          )}

          <div className="pt-2">
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 bg-[#141414] hover:bg-[#C8412B] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors disabled:opacity-50 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
            >
              {loading ? "Processing..." : isLogin ? "Sign In" : "Register"}
            </button>
          </div>
        </form>

        <p className="text-center text-xs text-[#5E5A52] font-['Jost',sans-serif] pt-2 border-t border-[#D9D3C7]/60">
          {isLogin ? "Don't have an account? " : "Already have an account? "}
          <button
            type="button"
            onClick={() => navigateTo(isLogin ? "register" : "login")}
            className="font-bold text-[#C8412B] hover:underline uppercase tracking-wider cursor-pointer ml-1"
          >
            {isLogin ? "Register" : "Sign In"}
          </button>
        </p>
      </div>
    </div>
  );
};

export default AuthForm;
