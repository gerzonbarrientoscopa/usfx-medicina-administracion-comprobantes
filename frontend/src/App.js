import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppLayout } from "@/components/AppLayout";
import { Toaster } from "@/components/ui/sonner";

import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import EstudiantesPage from "@/pages/EstudiantesPage";
import TiposPagosPage from "@/pages/TiposPagosPage";
import UsuariosPage from "@/pages/UsuariosPage";
import AnularPagoPage from "@/pages/AnularPagoPage";
import ReportesPage from "@/pages/ReportesPage";
import RegistroPagoPage from "@/pages/RegistroPagoPage";
import BusquedaPagosPage from "@/pages/BusquedaPagosPage";

function withLayout(element) {
    return (
        <ProtectedRoute>
            <AppLayout>{element}</AppLayout>
        </ProtectedRoute>
    );
}

function App() {
    return (
        <AuthProvider>
            <BrowserRouter>
                <Routes>
                    <Route path="/login" element={<LoginPage />} />

                    <Route path="/" element={withLayout(<DashboardPage />)} />

                    <Route
                        path="/estudiantes"
                        element={
                            <ProtectedRoute roles={["admin"]}>
                                <AppLayout>
                                    <EstudiantesPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/tipospagos"
                        element={
                            <ProtectedRoute roles={["admin"]}>
                                <AppLayout>
                                    <TiposPagosPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/usuarios"
                        element={
                            <ProtectedRoute roles={["admin"]}>
                                <AppLayout>
                                    <UsuariosPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/anular"
                        element={
                            <ProtectedRoute roles={["admin"]}>
                                <AppLayout>
                                    <AnularPagoPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/reportes"
                        element={
                            <ProtectedRoute roles={["admin"]}>
                                <AppLayout>
                                    <ReportesPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/registro"
                        element={
                            <ProtectedRoute roles={["admin", "caja"]}>
                                <AppLayout>
                                    <RegistroPagoPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/buscar"
                        element={
                            <ProtectedRoute roles={["admin", "caja", "consultas"]}>
                                <AppLayout>
                                    <BusquedaPagosPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />

                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
                <Toaster position="top-right" richColors />
            </BrowserRouter>
        </AuthProvider>
    );
}

export default App;
