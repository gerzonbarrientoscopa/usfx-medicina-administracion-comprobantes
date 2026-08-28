import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export function ProtectedRoute({ children, roles }) {
    const { user, loading } = useAuth();
    const location = useLocation();

    if (loading)
        return (
            <div className="h-screen w-full flex items-center justify-center bg-paper">
                <div className="text-sm text-[color:var(--institution-muted)]">Cargando…</div>
            </div>
        );

    if (!user) return <Navigate to="/login" replace state={{ from: location }} />;

    if (roles && roles.length > 0 && !roles.includes(user.role)) {
        return <Navigate to="/" replace />;
    }
    return children;
}
