import React from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import {
    LayoutDashboard,
    Users,
    GraduationCap,
    Tags,
    FileX,
    FileBarChart,
    Receipt,
    Search,
    LogOut,
    UserCog,
    Building2,
} from "lucide-react";

const NAV_BY_ROLE = {
    Administrador: [
        { to: "/", icon: LayoutDashboard, label: "Panel General" },
        { section: "Gestión" },
        { to: "/estudiantes", icon: GraduationCap, label: "Estudiantes" },
        { to: "/tipos-pagos", icon: Tags, label: "Tipos de Pago" },
        { to: "/usuarios", icon: UserCog, label: "Usuarios" },
        { section: "Operaciones" },
        { to: "/anular", icon: FileX, label: "Anular Pago" },
        { to: "/reportes", icon: FileBarChart, label: "Reportes" },
        { to: "/buscar", icon: Search, label: "Búsqueda Pagos" },
    ],
    Caja: [
        { to: "/", icon: LayoutDashboard, label: "Panel General" },
        { section: "Caja" },
        { to: "/registro", icon: Receipt, label: "Registro de Pago" },
        { to: "/buscar", icon: Search, label: "Búsqueda Pagos" },
    ],
    Consultas: [
        { to: "/", icon: LayoutDashboard, label: "Panel General" },
        { section: "Consultas" },
        { to: "/buscar", icon: Search, label: "Búsqueda Pagos" },
    ],
    SuperAdmin: [
        { to: "/", icon: LayoutDashboard, label: "Panel General" },
        { section: "Gestión" },
        { to: "/oficinas", icon: Building2, label: "Oficinas" },
        { to: "/usuarios", icon: UserCog, label: "Usuarios" },
        { to: "/estudiantes", icon: GraduationCap, label: "Estudiantes" },
        { to: "/tipos-pagos", icon: Tags, label: "Tipos de Pago" },
        { section: "Operaciones" },
        { to: "/registro", icon: Receipt, label: "Registro de Pago" },
        { to: "/buscar", icon: Search, label: "Búsqueda Pagos" },
        { to: "/anular", icon: FileX, label: "Anular Pago" },
        { to: "/reportes", icon: FileBarChart, label: "Reportes" },
    ],
};

const ROLE_LABEL = {
    Administrador: "Administrador",
    Caja: "Caja",
    Consultas: "Consultas",
    SuperAdmin: "SuperAdmin",
};

export function AppLayout({ children }) {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const items = NAV_BY_ROLE[user?.rol] || [];

    return (
        <div className="min-h-screen bg-paper flex">
            {/* Sidebar */}
            <aside
                className="w-64 shrink-0 bg-white border-r flex flex-col"
                style={{ borderColor: "var(--institution-border)" }}
                data-testid="app-sidebar"
            >
                <Link
                    to="/"
                    className="px-5 py-5 border-b flex items-center gap-3"
                    style={{ borderColor: "var(--institution-border)" }}
                >
                    <div
                        className="w-10 h-10 flex items-center justify-center text-white font-serif-display text-xl"
                        style={{ backgroundColor: "var(--institution-burgundy)" }}
                    >
                        U
                    </div>
                    <div className="leading-tight">
                        <div className="font-serif-display text-base font-semibold" style={{ color: "var(--institution-navy)" }}>
                            USFX
                        </div>
                        <div className="text-[10px] uppercase tracking-widest text-[color:var(--institution-muted)]">
                            Comprobantes
                        </div>
                    </div>
                </Link>

                <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
                    {items.map((it, idx) =>
                        it.section ? (
                            <div key={`sec-${idx}`} className="section-eyebrow px-3 pt-4 pb-1">
                                {it.section}
                            </div>
                        ) : (
                            <NavLink
                                key={it.to}
                                to={it.to}
                                end={it.to === "/"}
                                className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
                                data-testid={`nav-${it.to.replace("/", "") || "home"}`}
                            >
                                <it.icon size={18} strokeWidth={1.6} />
                                <span>{it.label}</span>
                            </NavLink>
                        ),
                    )}
                </nav>

                <div className="border-t p-3" style={{ borderColor: "var(--institution-border)" }}>
                    <div className="px-2 pb-2">
                        <div className="text-sm font-medium">{user?.nombre}</div>
                        <div className="text-xs text-[color:var(--institution-muted)]">
                            {ROLE_LABEL[user?.rol] || user?.rol}
                        </div>
                        <div className="text-xs text-[color:var(--institution-muted)] mt-1">
                            {user?.rol === "SuperAdmin"
                                ? "Todas las oficinas"
                                : user?.office_nombre}
                        </div>
                    </div>
                    <button
                        onClick={async () => {
                            await logout();
                            navigate("/login");
                        }}
                        className="w-full sidebar-link"
                        data-testid="logout-button"
                    >
                        <LogOut size={16} strokeWidth={1.6} />
                        <span>Cerrar sesión</span>
                    </button>
                </div>
            </aside>

            {/* Content */}
            <main className="flex-1 overflow-x-hidden">
                <header
                    className="h-14 bg-white border-b px-8 flex items-center justify-between"
                    style={{ borderColor: "var(--institution-border)" }}
                >
                    <div>
                        <div className="text-[10px] uppercase tracking-widest text-[color:var(--institution-muted)]">
                            Universidad Mayor, Real y Pontificia de San Francisco Xavier
                        </div>
                        <div className="text-xs font-medium" style={{ color: "var(--institution-burgundy)" }}>
                            {user?.rol === "SuperAdmin"
                                ? "Administración · Todas las oficinas"
                                : user?.office_nombre || "Administración de comprobantes"}
                        </div>
                    </div>
                    <div className="text-xs text-[color:var(--institution-muted)]">
                        {new Date().toLocaleDateString("es-BO", {
                            weekday: "long",
                            day: "numeric",
                            month: "long",
                            year: "numeric",
                        })}
                    </div>
                </header>
                <div className="p-8">{children}</div>
            </main>
        </div>
    );
}
