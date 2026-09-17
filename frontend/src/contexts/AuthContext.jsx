import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
} from "react";
import { apiClient, formatApiError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/auth/me");
      setUser(data);
    } catch (_e) {
      setUser(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
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
