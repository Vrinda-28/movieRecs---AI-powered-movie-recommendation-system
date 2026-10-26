import React from "react";
import { useAuth } from "../../contexts/AuthContext";
import { useAppContext } from "../../contexts/AppContext";
import { Menu, X, User, LogOut, Bookmark, Star, Sparkles, Shield } from "lucide-react";

/**
 * Editorial Navbar:
 * - Transparent with dark-to-transparent scrim over hero sections (Home & MovieDetail)
 * - Solid warm paper (#FAF7F2) with hairline divider elsewhere
 * - Clean typographic wordmark "MovieRecs"
 * - Fully accessible mobile navigation with aria-expanded
 */
const Navbar = ({ onLogout }) => {
  const { isAuthenticated, isAdmin, currentUser } = useAuth();
  const { currentPage, navigateTo, isMobileMenuOpen, setIsMobileMenuOpen } =
    useAppContext();

  const isHeroPage = currentPage === "home" || currentPage === "movieDetail";

  const navItems = [
    {
      name: "Home",
      page: "home",
      icon: <Star className="w-4 h-4" />,
      requiresAuth: false,
    },
    {
      name: "Recommendations",
      page: "recommendations",
      icon: <Sparkles className="w-4 h-4" />,
      requiresAuth: true,
    },
    {
      name: "Watchlist",
      page: "watchlist",
      icon: <Bookmark className="w-4 h-4" />,
      requiresAuth: true,
    },
    {
      name: "Admin",
      page: "admin",
      icon: <Shield className="w-4 h-4" />,
      requiresAuth: true,
      requiresAdmin: true,
    },
  ];

  const handleNav = (page) => {
    navigateTo(page);
    setIsMobileMenuOpen(false);
  };

  return (
    <header
      className={`sticky top-0 z-50 transition-colors duration-200 ${
        isHeroPage
          ? "bg-[#141414]/90 backdrop-blur-md text-[#FAF7F2] border-b border-white/10"
          : "bg-[#FAF7F2] text-[#141414] border-b border-[#D9D3C7]"
      }`}
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Wordmark */}
          <div className="flex items-center">
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                handleNav("home");
              }}
              className="flex items-center group focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
              aria-label="MovieRecs home"
            >
              <span className="font-['Jost',sans-serif] font-black text-xl sm:text-2xl tracking-[0.12em] uppercase transition-colors group-hover:text-[#C8412B]">
                MOVIERECS
              </span>
            </a>
          </div>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center space-x-6" aria-label="Main navigation">
            {navItems.map((item) => {
              if (item.requiresAuth && !isAuthenticated) return null;
              if (item.requiresAdmin && !isAdmin) return null;
              const isActive = currentPage === item.page;

              return (
                <a
                  key={item.page}
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    handleNav(item.page);
                  }}
                  className={`font-['Jost',sans-serif] text-xs uppercase tracking-widest font-bold transition-all py-1 border-b-2 ${
                    isActive
                      ? isHeroPage
                        ? "border-[#C8412B] text-white"
                        : "border-[#C8412B] text-[#C8412B]"
                      : isHeroPage
                      ? "border-transparent text-white/80 hover:text-white hover:border-white/40"
                      : "border-transparent text-[#5E5A52] hover:text-[#141414] hover:border-[#141414]"
                  }`}
                >
                  {item.name}
                </a>
              );
            })}
          </nav>

          {/* Desktop Auth Controls */}
          <div className="hidden md:flex items-center space-x-4">
            {isAuthenticated ? (
              <div className="flex items-center space-x-3">
                <button
                  type="button"
                  onClick={() => handleNav("profile")}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-['Jost',sans-serif] font-bold uppercase tracking-wider border transition-colors cursor-pointer ${
                    currentPage === "profile"
                      ? "bg-[#C8412B] text-white border-[#C8412B]"
                      : isHeroPage
                      ? "bg-transparent text-white border-white/30 hover:border-white"
                      : "bg-white text-[#141414] border-[#D9D3C7] hover:border-[#141414]"
                  }`}
                >
                  <User className="w-3.5 h-3.5" />
                  <span className="max-w-[120px] truncate">
                    {currentUser?.email ? currentUser.email.split("@")[0] : "Profile"}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={onLogout}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-['Jost',sans-serif] font-semibold uppercase tracking-wider transition-colors cursor-pointer ${
                    isHeroPage
                      ? "text-white/70 hover:text-[#C8412B]"
                      : "text-[#5E5A52] hover:text-[#C8412B]"
                  }`}
                  aria-label="Log out"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span>Logout</span>
                </button>
              </div>
            ) : (
              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={() => handleNav("login")}
                  className={`px-3 py-1.5 text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors cursor-pointer ${
                    isHeroPage
                      ? "text-white/80 hover:text-white"
                      : "text-[#141414] hover:text-[#C8412B]"
                  }`}
                >
                  Login
                </button>
                <button
                  type="button"
                  onClick={() => handleNav("register")}
                  className="px-4 py-1.5 bg-[#C8412B] hover:bg-[#A8321F] text-white text-xs font-['Jost',sans-serif] font-bold uppercase tracking-widest transition-colors shadow-sm cursor-pointer"
                >
                  Join
                </button>
              </div>
            )}
          </div>

          {/* Mobile Menu Toggle Button */}
          <div className="md:hidden">
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="p-2 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8412B]"
              aria-label="Toggle navigation menu"
              aria-expanded={isMobileMenuOpen}
            >
              {isMobileMenuOpen ? (
                <X className="w-6 h-6" />
              ) : (
                <Menu className="w-6 h-6" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Accessible Mobile Drawer */}
      {isMobileMenuOpen && (
        <div className="md:hidden fixed inset-x-0 top-16 bottom-0 bg-[#FAF7F2] text-[#141414] z-50 p-6 flex flex-col justify-between overflow-y-auto border-t border-[#D9D3C7]">
          <div className="space-y-4">
            <span className="text-[11px] font-['Jost',sans-serif] font-bold uppercase tracking-widest text-[#5E5A52] block border-b border-[#D9D3C7] pb-2">
              Menu
            </span>
            <div className="flex flex-col space-y-2">
              {navItems.map((item) => {
                if (item.requiresAuth && !isAuthenticated) return null;
                if (item.requiresAdmin && !isAdmin) return null;
                const isActive = currentPage === item.page;

                return (
                  <button
                    key={item.page}
                    type="button"
                    onClick={() => handleNav(item.page)}
                    className={`flex items-center gap-3 p-3 font-['Jost',sans-serif] font-bold text-sm uppercase tracking-wider text-left border ${
                      isActive
                        ? "bg-[#C8412B] text-white border-[#C8412B]"
                        : "bg-white text-[#141414] border-[#D9D3C7] hover:border-[#141414]"
                    }`}
                  >
                    {item.icon}
                    <span>{item.name}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Mobile Auth Actions */}
          <div className="pt-6 border-t border-[#D9D3C7] space-y-3">
            {isAuthenticated ? (
              <>
                <button
                  type="button"
                  onClick={() => handleNav("profile")}
                  className="w-full py-3 bg-white border border-[#D9D3C7] text-[#141414] font-['Jost',sans-serif] font-bold text-xs uppercase tracking-wider flex items-center justify-center gap-2"
                >
                  <User className="w-4 h-4" />
                  <span>My Profile ({currentUser?.email?.split("@")[0]})</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onLogout();
                    setIsMobileMenuOpen(false);
                  }}
                  className="w-full py-3 bg-[#141414] text-white font-['Jost',sans-serif] font-bold text-xs uppercase tracking-wider flex items-center justify-center gap-2"
                >
                  <LogOut className="w-4 h-4" />
                  <span>Logout</span>
                </button>
              </>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => handleNav("login")}
                  className="py-3 bg-white border border-[#D9D3C7] text-[#141414] font-['Jost',sans-serif] font-bold text-xs uppercase tracking-wider text-center"
                >
                  Login
                </button>
                <button
                  type="button"
                  onClick={() => handleNav("register")}
                  className="py-3 bg-[#C8412B] text-white font-['Jost',sans-serif] font-bold text-xs uppercase tracking-wider text-center"
                >
                  Register
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
};

export default Navbar;
