import React, { createContext, useState, useEffect, useContext, useCallback } from "react";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loadingUser, setLoadingUser] = useState(true);

  const logout = useCallback(() => {
    localStorage.removeItem("authToken");
    setToken(null);
    setCurrentUser(null);
    setIsAdmin(false);
  }, []);

  const login = useCallback((newToken, userData) => {
    localStorage.setItem("authToken", newToken);
    setToken(newToken);
    setCurrentUser(userData);
    setIsAdmin(Boolean(userData?.is_admin));
  }, []);

  // Check auth state on initial mount
  useEffect(() => {
    const storedToken = localStorage.getItem("authToken");
    if (storedToken) {
      setToken(storedToken);
      fetch(`${API_BASE_URL}/api/v1/users/me`, {
        headers: { Authorization: `Bearer ${storedToken}` },
      })
        .then((res) => {
          if (res.ok) {
            return res.json();
          }
          if (res.status === 401 || res.status === 403) {
            logout();
            return Promise.reject(new Error("Token expired"));
          }
          return Promise.reject(new Error("Failed to validate user"));
        })
        .then((data) => {
          setCurrentUser(data);
          setIsAdmin(Boolean(data?.is_admin));
        })
        .catch(() => {
          logout();
        })
        .finally(() => {
          setLoadingUser(false);
        });
    } else {
      setLoadingUser(false);
    }
  }, [logout]);

  // Listen for global 401 unauthorized events triggered mid-session
  useEffect(() => {
    const handleUnauthorizedEvent = () => {
      logout();
    };

    window.addEventListener("auth:unauthorized", handleUnauthorizedEvent);
    return () => {
      window.removeEventListener("auth:unauthorized", handleUnauthorizedEvent);
    };
  }, [logout]);

  return (
    <AuthContext.Provider
      value={{
        token,
        currentUser,
        isAdmin,
        login,
        logout,
        loadingUser,
        isAuthenticated: Boolean(token && currentUser),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
