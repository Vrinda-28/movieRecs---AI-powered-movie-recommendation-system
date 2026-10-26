const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

/**
 * Dispatches a global unauthorized event and clears local storage token
 * to ensure mid-session 401s reset authentication and prompt login.
 */
function handleGlobal401() {
  localStorage.removeItem("authToken");
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent("auth:unauthorized", {
        detail: { message: "Session expired or token invalid. Please log in again." },
      }),
    );
  }
}

const ApiService = {
  async request(endpoint, options = {}) {
    const { body, method = "GET", token, isFormData = false, signal } = options;
    const headers = isFormData ? {} : { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const config = { method, headers };
    if (signal) config.signal = signal;
    if (body) config.body = isFormData ? body : JSON.stringify(body);

    let response;
    try {
      response = await fetch(`${API_BASE_URL}${endpoint}`, config);
    } catch (networkError) {
      if (networkError.name === "AbortError") {
        throw networkError;
      }
      const error = new Error(
        networkError.message || "Network error. Backend service may be offline.",
      );
      error.isNetworkError = true;
      throw error;
    }

    // Global 401 / 403 Session Expiry Interceptor
    if (response.status === 401) {
      handleGlobal401();
    }

    if (!response.ok) {
      let errorData;
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        errorData = await response.json().catch(() => ({
          message: `API request failed with status ${response.status}`,
        }));
      } else {
        const errorText = await response
          .text()
          .catch(() => `API request failed with status ${response.status}.`);
        errorData = { message: errorText };
      }

      const errorMessage =
        errorData.detail?.[0]?.msg ||
        (typeof errorData.detail === "string" ? errorData.detail : null) ||
        errorData.message ||
        `API request failed: ${response.status}`;
      const error = new Error(errorMessage);
      error.status = response.status;
      error.response = response;
      error.data = errorData;
      error.detail =
        typeof errorData.detail === "string"
          ? errorData.detail
          : errorData.detail?.[0]?.msg || null;
      throw error;
    }

    if (
      response.status === 204 ||
      response.headers.get("content-length") === "0"
    ) {
      return null;
    }
    return response.json();
  },

  registerUser: (userData) =>
    ApiService.request("/api/v1/users/register", {
      method: "POST",
      body: userData,
    }),

  loginUser: async (credentials) => {
    const formData = new URLSearchParams();
    formData.append("username", credentials.username);
    formData.append("password", credentials.password);

    const response = await fetch(`${API_BASE_URL}/api/v1/users/login/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData,
    });

    if (!response.ok) {
      let errorData;
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        errorData = await response.json().catch(() => ({
          message: `Login failed with status ${response.status}`,
        }));
      } else {
        const errorText = await response.text().catch(() => "Login failed.");
        errorData = { message: errorText };
      }
      const errorMessage =
        errorData.detail?.[0]?.msg ||
        errorData.detail ||
        errorData.message ||
        "Incorrect email or password";
      const error = new Error(errorMessage);
      error.status = response.status;
      error.response = response;
      error.data = errorData;
      throw error;
    }
    return response.json();
  },

  getCurrentUser: (token) => ApiService.request("/api/v1/users/me", { token }),

  getMovies: (skip = 0, limit = 12, token = null, search = null, genres = null) => {
    const params = new URLSearchParams({
      skip: skip.toString(),
      limit: limit.toString(),
    });
    if (search && search.trim()) {
      params.append("search", search.trim());
    }
    if (genres && genres.trim()) {
      params.append("genres", genres.trim());
    }
    return ApiService.request(`/api/v1/movies/?${params.toString()}`, {
      token,
    });
  },

  getMovieById: (movieId, token = null) =>
    ApiService.request(`/api/v1/movies/${movieId}`, { token }),

  createMovie: (movieData, token) =>
    ApiService.request("/api/v1/movies/", {
      method: "POST",
      body: movieData,
      token,
    }),

  rateMovie: (ratingData, token) =>
    ApiService.request("/api/v1/ratings/", {
      method: "POST",
      body: ratingData,
      token,
    }),

  getMyRecommendations: (token, count = 10, exclude_watched = true) =>
    ApiService.request(
      `/api/v1/recommendations/user/me?count=${count}&exclude_watched=${exclude_watched}`,
      { token },
    ),

  getOnboardingMovies: (total = 16) =>
    ApiService.request(`/api/v1/movies/onboarding?total=${total}`),

  getInferenceTrace: (token, count = 10) =>
    ApiService.request(
      `/api/v1/recommendations/debug/me?count=${count}`,
      { token },
    ),

  triggerRetrainModel: (token) =>
    ApiService.request("/api/v1/admin/trigger-retrain-model", {
      method: "POST",
      token,
    }),

  logInteraction: async (interactionData, token = null) => {
    try {
      return await ApiService.request("/api/v1/interactions/", {
        method: "POST",
        body: interactionData,
        token,
      });
    } catch {
      // Failures must be silent to the user
      return null;
    }
  },

  deleteMovie: (movieId, token) =>
    ApiService.request(`/api/v1/movies/${movieId}`, {
      method: "DELETE",
      token,
    }),

  // Reviews
  getMovieReviews: (movieId, skip = 0, limit = 10) =>
    ApiService.request(
      `/api/v1/reviews/movies/${movieId}?skip=${skip}&limit=${limit}`,
    ),

  createReview: (reviewData, token) =>
    ApiService.request("/api/v1/reviews/", {
      method: "POST",
      body: reviewData,
      token,
    }),

  updateReview: (reviewId, reviewData, token) =>
    ApiService.request(`/api/v1/reviews/${reviewId}`, {
      method: "PUT",
      body: reviewData,
      token,
    }),

  deleteReview: (reviewId, token) =>
    ApiService.request(`/api/v1/reviews/${reviewId}`, {
      method: "DELETE",
      token,
    }),

  // Watchlist
  addToWatchlist: (movieId, token) =>
    ApiService.request(`/api/v1/watchlist/${movieId}`, {
      method: "POST",
      token,
    }),

  removeFromWatchlist: (movieId, token) =>
    ApiService.request(`/api/v1/watchlist/${movieId}`, {
      method: "DELETE",
      token,
    }),

  getMyWatchlist: (token, skip = 0, limit = 50) =>
    ApiService.request(`/api/v1/watchlist/?skip=${skip}&limit=${limit}`, {
      token,
    }),

  checkWatchlist: (movieId, token) =>
    ApiService.request(`/api/v1/watchlist/check/${movieId}`, {
      token,
    }),

  // User History & Ratings
  getMyRatings: (token, skip = 0, limit = 100) =>
    ApiService.request(`/api/v1/ratings/user/me?skip=${skip}&limit=${limit}`, {
      token,
    }),

  getUserHistory: (token, skip = 0, limit = 50) =>
    ApiService.request(`/api/v1/users/me/history?skip=${skip}&limit=${limit}`, {
      token,
    }),

  // Admin Diagnostics & Model Management
  getSystemHealth: (token) =>
    ApiService.request("/api/v1/admin/system-health", { token }),

  getDatabaseCounts: (token) =>
    ApiService.request("/api/v1/admin/database-counts", { token }),

  getModelInfo: (token) =>
    ApiService.request("/api/v1/admin/model-info", { token }),

  getLatestEvaluation: (token) =>
    ApiService.request("/api/v1/admin/latest-evaluation", { token }),

  getLatestTrainingStatus: (token) =>
    ApiService.request("/api/v1/admin/training-status/latest", { token }),

  getTaskTrainingStatus: (taskId, token) =>
    ApiService.request(`/api/v1/admin/training-status/${taskId}`, { token }),

  getModelVersions: (token) =>
    ApiService.request("/api/v1/admin/models/versions", { token }),

  rollbackModelVersion: (versionName, token) =>
    ApiService.request("/api/v1/admin/models/rollback", {
      method: "POST",
      body: { version_name: versionName },
      token,
    }),

  // Gemini AI Features
  getAiStatus: (signal) => ApiService.request("/api/v1/ai/status", { signal }),

  aiDiscover: (prompt, token, signal) =>
    ApiService.request("/api/v1/ai/discover", {
      method: "POST",
      body: { prompt },
      token,
      signal,
    }),

  aiAsk: ({ question, movieId = null, history = [] }, token, signal) =>
    ApiService.request("/api/v1/ai/ask", {
      method: "POST",
      body: {
        question,
        movie_id: movieId,
        history,
      },
      token,
      signal,
    }),
};

export default ApiService;
