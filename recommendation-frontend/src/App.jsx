import React, { useEffect } from "react";
import { useAuth } from "./contexts/AuthContext";
import { useAppContext } from "./contexts/AppContext";
import ApiService from "./services/ApiService";

import Navbar from "./components/Layout/Navbar";
import Footer from "./components/Layout/Footer";
import AuthForm from "./components/Auth/AuthForm";
import HomePage from "./pages/HomePage";
import RecommendationsPage from "./pages/RecommendationsPage";
import AdminPage from "./components/Admin/AdminPage";
import MovieDetailPage from "./pages/MovieDetailPage";
import WatchlistPage from "./pages/WatchlistPage";
import ProfilePage from "./pages/ProfilePage";
import OnboardingPage from "./pages/OnboardingPage";
import MessageBox from "./components/Common/MessageBox";
import LoadingSpinner from "./components/Common/LoadingSpinner";

const App = () => {
  const { isAuthenticated, isAdmin, logout, loadingUser, login } = useAuth();
  const {
    currentPage,
    navigateTo,
    globalMessage,
    showGlobalMessage,
    selectedMovieId,
  } = useAppContext();

  // Login/Register handlers
  const handleLoginSubmit = async (credentials) => {
    try {
      const tokenData = await ApiService.loginUser(credentials);
      const userData = await ApiService.getCurrentUser(tokenData.access_token);
      login(tokenData.access_token, userData);
      
      // Check if user has any ratings; if not, prompt onboarding
      try {
        const myRatings = await ApiService.getMyRatings(tokenData.access_token);
        if (!myRatings || myRatings.length === 0) {
          navigateTo("onboarding");
          showGlobalMessage("Welcome! Rate a few movies to personalize your recommendations.", "info");
          return;
        }
      } catch {
        // ignore check failure, go home
      }

      navigateTo("home");
      showGlobalMessage("Login successful! Welcome back.", "success");
    } catch (err) {
      showGlobalMessage(err.message || "Failed to log in", "error");
    }
  };

  const handleRegisterSubmit = async (credentials) => {
    try {
      await ApiService.registerUser({
        email: credentials.username,
        password: credentials.password,
      });
      navigateTo("login");
      showGlobalMessage("Registration successful! Please log in.", "success");
    } catch (err) {
      showGlobalMessage(err.message || "Failed to register", "error");
    }
  };

  const handleLogout = () => {
    logout();
    navigateTo("login");
    showGlobalMessage("You have been logged out.", "success");
  };

  // Effect for redirecting if not authenticated or not admin for protected routes
  useEffect(() => {
    if (!loadingUser) {
      const isRecommendationsPage = currentPage === "recommendations";
      const isAdminPage = currentPage === "admin";

      if (isRecommendationsPage && !isAuthenticated) {
        showGlobalMessage("Please log in to view recommendations.", "error");
        navigateTo("login");
      } else if (isAdminPage) {
        if (!isAuthenticated) {
          showGlobalMessage("Please log in to access the admin panel.", "error");
          navigateTo("login");
        } else if (!isAdmin) {
          showGlobalMessage("You do not have permission to access the admin page.", "error");
          navigateTo("home");
        }
      }
    }
  }, [
    currentPage,
    isAuthenticated,
    isAdmin,
    loadingUser,
    navigateTo,
    showGlobalMessage,
  ]);

  if (loadingUser) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#FAF7F2] text-[#141414]">
        <LoadingSpinner text="Loading MovieRecs..." />
      </div>
    );
  }

  // Determine the page component to render
  let pageComponent;
  switch (currentPage) {
    case "home":
      pageComponent = <HomePage />;
      break;
    case "login":
      pageComponent = <AuthForm isLogin={true} onSubmit={handleLoginSubmit} />;
      break;
    case "register":
      pageComponent = (
        <AuthForm isLogin={false} onSubmit={handleRegisterSubmit} />
      );
      break;
    case "recommendations":
      pageComponent = isAuthenticated ? (
        <RecommendationsPage />
      ) : (
        <LoadingSpinner text="Redirecting..." />
      );
      break;
    case "admin":
      pageComponent =
        isAuthenticated && isAdmin ? (
          <AdminPage />
        ) : (
          <LoadingSpinner text="Redirecting..." />
        );
      break;
    case "movieDetail":
      pageComponent = selectedMovieId ? <MovieDetailPage /> : <HomePage />;
      break;
    case "watchlist":
      pageComponent = <WatchlistPage />;
      break;
    case "profile":
      pageComponent = <ProfilePage />;
      break;
    case "onboarding":
      pageComponent = <OnboardingPage />;
      break;
    default:
      pageComponent = <HomePage />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-[#FAF7F2] text-[#141414] overflow-x-hidden">
      <MessageBox
        message={globalMessage.text}
        type={globalMessage.type}
        onDismiss={() => showGlobalMessage("", "")}
      />
      <Navbar onLogout={handleLogout} />
      <main className="flex-grow w-full">
        {pageComponent}
      </main>
      <Footer />
    </div>
  );
};

export default App;
