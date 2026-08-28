import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
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
            localStorage.setItem("token", data.token);
            setUser(data.user);
            return { ok: true, user: data.user };
        } catch (e) {
            return { ok: false, error: formatApiError(e) };
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
