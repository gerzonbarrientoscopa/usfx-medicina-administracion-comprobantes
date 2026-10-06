import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppLayout } from "@/components/AppLayout";
import { Toaster } from "@/components/ui/sonner";

import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import ClientesPage from "@/pages/ClientesPage";
import ConceptosRecaudacionPage from "@/pages/ConceptosRecaudacionPage";
import ClasificadoresPresupuestariosPage from "@/pages/ClasificadoresPresupuestariosPage";
import AmbientesPage from "@/pages/AmbientesPage";
import UsuariosPage from "@/pages/UsuariosPage";
import AnularPagoPage from "@/pages/AnularPagoPage";
import ReportesPage from "@/pages/ReportesPage";
import RegistroPagoPage from "@/pages/RegistroPagoPage";
import BusquedaPagosPage from "@/pages/BusquedaPagosPage";
import OficinasPage from "@/pages/OficinasPage";
import TarifarioAmbientesPage from "@/pages/TarifarioAmbientesPage";
import RegistroAlquilerPage from "@/pages/RegistroAlquilerPage";

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
                        path="/oficinas"
                        element={
                            <ProtectedRoute roles={["SuperAdmin"]}>
                                <AppLayout>
                                    <OficinasPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/clientes"
                        element={
                            <ProtectedRoute roles={["Administrador", "Caja"]}>
                                <AppLayout>
                                    <ClientesPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/conceptos-recaudacion"
                        element={
                            <ProtectedRoute roles={["Administrador"]}>
                                <AppLayout>
                                    <ConceptosRecaudacionPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/clasificadores-presupuestarios"
                        element={
                            <ProtectedRoute roles={["SuperAdmin"]}>
                                <AppLayout>
                                    <ClasificadoresPresupuestariosPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/tipos-pagos"
                        element={<Navigate to="/conceptos-recaudacion" replace />}
                    />
                    <Route
                        path="/ambientes"
                        element={
                            <ProtectedRoute roles={["Administrador"]}>
                                <AppLayout>
                                    <AmbientesPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/tarifario-ambientes"
                        element={
                            <ProtectedRoute roles={["Administrador", "SuperAdmin"]}>
                                <AppLayout>
                                    <TarifarioAmbientesPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/usuarios"
                        element={
                            <ProtectedRoute roles={["SuperAdmin"]}>
                                <AppLayout>
                                    <UsuariosPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/anular"
                        element={
                            <ProtectedRoute roles={["Administrador", "Caja"]}>
                                <AppLayout>
                                    <AnularPagoPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/reportes"
                        element={
                            <ProtectedRoute roles={["Administrador"]}>
                                <AppLayout>
                                    <ReportesPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/registro"
                        element={
                            <ProtectedRoute roles={["Administrador", "Caja", "SuperAdmin"]}>
                                <AppLayout>
                                    <RegistroPagoPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/registro-alquiler"
                        element={
                            <ProtectedRoute roles={["Administrador", "Caja", "SuperAdmin"]}>
                                <AppLayout>
                                    <RegistroAlquilerPage />
                                </AppLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/buscar"
                        element={
                            <ProtectedRoute roles={["Administrador", "Caja", "Consultas"]}>
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
