import React from "react";
import { useAppContext } from "../../contexts/AppContext";
import { useAuth } from "../../contexts/AuthContext";

/**
 * Editorial SiteFooter:
 * - Four semantic columns: Wordmark/Institution, How recommendations work, Site Navigation, TMDB Attribution
 * - Zero inert controls (no fake newsletter or inactive forms)
 * - Thin coral bottom bar with college academic attribution
 */
const Footer = () => {
  const { navigateTo } = useAppContext();
  const { isAuthenticated, isAdmin } = useAuth();

  const handleNav = (page) => {
    navigateTo(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <footer className="w-full bg-white text-[#141414] border-t border-[#D9D3C7] mt-auto">
      {/* Main 4-column content band */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 lg:gap-12">
          {/* Column 1: Wordmark & College */}
          <div className="space-y-3">
            <h3 className="font-['Jost',sans-serif] font-black text-xl tracking-[0.12em] uppercase text-[#141414]">
              MOVIERECS
            </h3>
            <p className="text-xs text-[#5E5A52] leading-relaxed">
              An AI-powered sequential recommendation and discovery system designed for cinema enthusiasts.
            </p>
            <p className="text-xs text-[#5E5A52] font-medium pt-1">
              Shah & Anchor Kutchhi Engineering College
            </p>
          </div>

          {/* Column 2: How recommendations work */}
          <div className="space-y-3">
            <h4 className="font-['Jost',sans-serif] font-bold text-xs uppercase tracking-widest text-[#141414] border-b border-[#D9D3C7] pb-1.5">
              How Recommendations Work
            </h4>
            <p className="text-xs text-[#5E5A52] leading-relaxed">
              A GRU-based sequential neural model analyzes your rating chronology to predict your next preferred films. For members with sparse interaction history, a popularity-weighted baseline provides immediate discovery.
            </p>
          </div>

          {/* Column 3: Site Navigation (active routes only) */}
          <div className="space-y-3">
            <h4 className="font-['Jost',sans-serif] font-bold text-xs uppercase tracking-widest text-[#141414] border-b border-[#D9D3C7] pb-1.5">
              Explore
            </h4>
            <ul className="space-y-2 text-xs font-['Jost',sans-serif] font-semibold uppercase tracking-wider">
              <li>
                <button
                  type="button"
                  onClick={() => handleNav("home")}
                  className="text-[#5E5A52] hover:text-[#C8412B] transition-colors cursor-pointer"
                >
                  Catalogue Home
                </button>
              </li>
              {isAuthenticated && (
                <>
                  <li>
                    <button
                      type="button"
                      onClick={() => handleNav("recommendations")}
                      className="text-[#5E5A52] hover:text-[#C8412B] transition-colors cursor-pointer"
                    >
                      Recommendations
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => handleNav("watchlist")}
                      className="text-[#5E5A52] hover:text-[#C8412B] transition-colors cursor-pointer"
                    >
                      Your Watchlist
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => handleNav("profile")}
                      className="text-[#5E5A52] hover:text-[#C8412B] transition-colors cursor-pointer"
                    >
                      Profile & Ratings
                    </button>
                  </li>
                </>
              )}
              {isAuthenticated && isAdmin && (
                <li>
                  <button
                    type="button"
                    onClick={() => handleNav("admin")}
                    className="text-[#5E5A52] hover:text-[#C8412B] transition-colors cursor-pointer"
                  >
                    System Admin
                  </button>
                </li>
              )}
            </ul>
          </div>

          {/* Column 4: TMDB Attribution */}
          <div className="space-y-3">
            <h4 className="font-['Jost',sans-serif] font-bold text-xs uppercase tracking-widest text-[#141414] border-b border-[#D9D3C7] pb-1.5">
              Data & Attribution
            </h4>
            <p className="text-xs text-[#5E5A52] leading-relaxed">
              This product uses the TMDB API but is not endorsed or certified by TMDB.
            </p>
            <p className="text-[11px] text-[#5E5A52] leading-relaxed pt-1">
              Rating behaviors and film catalogue grounded in the GroupLens MovieLens research dataset.
            </p>
          </div>
        </div>
      </div>

      {/* Thin coral bottom bar */}
      <div className="w-full bg-[#C8412B] text-white py-3 px-4 text-center">
        <p className="text-[11px] font-['Jost',sans-serif] font-medium tracking-wider uppercase text-white/95">
          © {new Date().getFullYear()} MovieRecs · Academic project, Shah & Anchor Kutchhi Engineering College
        </p>
      </div>
    </footer>
  );
};

export default Footer;
