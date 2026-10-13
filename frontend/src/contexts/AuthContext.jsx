import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
} from "react";
import { apiClient, formatApiError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const initialized = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const url = new URL(window.location.href);
      const ssoKeys = ["cu", "nu", "hu", "iu"];
      const hasInstitutionalLink = ssoKeys.every((key) =>
        url.searchParams.has(key),
      );
      if (hasInstitutionalLink) {
        const institutionalData = Object.fromEntries(
          ssoKeys.map((key) => [key, url.searchParams.get(key)]),
        );
        ssoKeys.forEach((key) => url.searchParams.delete(key));
        const remainingSearch = url.searchParams.toString();
        window.history.replaceState(
          window.history.state,
          "",
          `${url.pathname}${remainingSearch ? `?${remainingSearch}` : ""}${url.hash}`,
        );
        try {
          const { data } = await apiClient.post("/auth/sso", {
            ...institutionalData,
            hu: Number(institutionalData.hu),
          });
          const userData = data.user || data.usuario;
          localStorage.setItem("token", data.token);
          setUser(userData);
          return;
        } catch (_ssoError) {
          // An invalid institutional link must not discard a valid existing session.
        }
      }

      if (!localStorage.getItem("token")) {
        setUser(false);
        return;
      }
      const { data } = await apiClient.get("/auth/me");
      setUser(data);
    } catch (_e) {
      localStorage.removeItem("token");
      setUser(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    refresh();
  }, [refresh]);

  const login = async (email, password) => {
    try {
      const { data } = await apiClient.post("/auth/login", { email, password });
      // ADAPTACIÓN DE BACKEND: FastAPI envía 'usuario', lo extraemos con seguridad
      const userData = data.user || data.usuario;
      localStorage.setItem("token", data.token);
      setUser(userData);
      return { ok: true, success: true, user: userData };
    } catch (e) {
      return { ok: false, success: false, error: formatApiError(e) };
    }
  };

  const logout = async () => {
    try {
      await apiClient.post("/auth/logout");
    } catch (_e) {
      /* ignore */
    }
    localStorage.removeItem("token");
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth debe ser usado dentro de AuthProvider");
  }
  return context;
}
