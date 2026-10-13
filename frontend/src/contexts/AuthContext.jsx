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
const INSTITUTIONAL_QUERY_KEYS = ["cu", "nu", "hu", "iu"];

function classifyInstitutionalFailure(error) {
  const detail = error?.response?.data?.detail;
  const message = typeof detail === "string" ? detail.toLowerCase() : "";
  if (message.includes("expir") || message.includes("caduc")) {
    return { kind: "expired" };
  }
  if ([401, 403, 422].includes(error?.response?.status)) {
    return { kind: "unauthorized" };
  }
  return { kind: "unavailable" };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [institutionalAuthError, setInstitutionalAuthError] = useState(null);
  const initialized = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const url = new URL(window.location.href);
      const hasInstitutionalParameters = INSTITUTIONAL_QUERY_KEYS.some((key) =>
        url.searchParams.has(key),
      );
      if (hasInstitutionalParameters) {
        const institutionalData = Object.fromEntries(
          INSTITUTIONAL_QUERY_KEYS.map((key) => [
            key,
            url.searchParams.get(key),
          ]),
        );
        INSTITUTIONAL_QUERY_KEYS.forEach((key) =>
          url.searchParams.delete(key),
        );
        const remainingSearch = url.searchParams.toString();
        window.history.replaceState(
          window.history.state,
          "",
          `${url.pathname}${remainingSearch ? `?${remainingSearch}` : ""}${url.hash}`,
        );
        const isCompleteLink = INSTITUTIONAL_QUERY_KEYS.every(
          (key) => institutionalData[key] !== null,
        );
        if (!isCompleteLink) {
          localStorage.removeItem("token");
          setUser(false);
          setInstitutionalAuthError({ kind: "unauthorized" });
          return;
        }
        try {
          const { data } = await apiClient.post("/auth/sso", {
            ...institutionalData,
            hu: Number(institutionalData.hu),
          });
          const userData = data.user || data.usuario;
          localStorage.setItem("token", data.token);
          setUser(userData);
          setInstitutionalAuthError(null);
          return;
        } catch (ssoError) {
          localStorage.removeItem("token");
          setUser(false);
          setInstitutionalAuthError(
            classifyInstitutionalFailure(ssoError),
          );
          return;
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
      setInstitutionalAuthError(null);
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
    setInstitutionalAuthError(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, loading, login, logout, refresh, institutionalAuthError }}
    >
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
