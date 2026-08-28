import React, { useState } from "react";
import { useNavigate, useLocation, Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle} from "@/components/ui/card";
import { Banknote, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [correo, setCorreo] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  if (user) {
    const dest = location.state?.from?.pathname || "/";
    return <Navigate to={dest} replace />;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    const result = await login(correo.trim(), password);
    setLoading(false);
    if (result.ok) {
      toast.success("Inicio de sesión exitoso.");
      navigate("/", { replace: true });
    } else {
      toast.error(result.error || "Error al iniciar sesión.");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 bg-paper">
      <div className="w-full max-w-md">
        <Card className="rounded-sm border-[color:var(--institution-border)] shadow-none" data-testid="login-card">
          <CardHeader className="text-center space-y-4 pt-10 pb-4">
            <div className="flex justify-center">
              <div className="w-16 h-16 flex items-center justify-center text-white" style={{ backgroundColor: "var(--institution-burgundy)" }}>
                <Banknote size={30} strokeWidth={1.5} />
              </div>
            </div>
            <div>
              <div className="section-eyebrow mb-2">Acceso Institucional</div>
              <CardTitle className="font-serif-display text-3xl leading-tight" style={{ color: "var(--institution-text)" }}>
                Sistema Web Comprobantes Administración de la Facultad de Medicina
              </CardTitle>
            </div>
            <CardDescription className="text-sm text-[color:var(--institution-muted)] leading-relaxed px-2">
              Universidad Mayor, Real y Pontificia
              <br />
              de San Francisco Xavier
              <br />
              <span
                style={{ color: "var(--institution-burgundy)" }}
                className="font-medium"
              >
                Facultad de Medicina · Administración
              </span>
            </CardDescription>            
          </CardHeader>

          <CardContent className="pb-8">
            <form
              onSubmit={handleSubmit}
              className="space-y-5"
              data-testid="login-form"
            >
              <div className="space-y-1.5">
                <Label
                  htmlFor="correo"
                  className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)] font-semibold"
                >
                  Correo Electrónico
                </Label>
                <Input
                  id="correo"
                  type="email"
                  value={correo}
                  onChange={(e) => setCorreo(e.target.value)}
                  required
                  autoComplete="username"
                  data-testid="login-email-input"
                  className="rounded-sm border-[color:var(--institution-border)] bg-[color:var(--institution-cream)] h-11"
                />
              </div>

              <div className="space-y-1.5">
                <Label
                  htmlFor="password"
                  className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)] font-semibold"
                >
                  Contraseña
                </Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  data-testid="login-password-input"
                  className="rounded-sm border-[color:var(--institution-border)] bg-[color:var(--institution-cream)] h-11"
                />
              </div>

              <Button
                type="submit"
                disabled={loading}
                data-testid="login-submit-button"
                className="w-full h-11 rounded-sm text-white font-medium tracking-wide uppercase text-xs"
                style={{ backgroundColor: "var(--institution-burgundy)" }}
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="animate-spin" size={16} /> Iniciando…
                  </span>
                ) : (
                  "Iniciar Sesión"
                )}
              </Button>
            </form>

            <div
              className="mt-8 pt-5 border-t flex justify-center"
              style={{ borderColor: "var(--institution-border)" }}
            >
              <img
                src="https://customer-assets.emergentagent.com/job_edu-payment-portal-1/artifacts/1v4rfrby_Logo%20GerabDevSoft.png"
                alt="GerabDevSoft · Desarrollo de Software · 68662738"
                className="h-24 w-auto select-none"
                data-testid="gerabdevsoft-logo"
                draggable={false}
              />
            </div>
          </CardContent>
        </Card>

        <div className="mt-6 text-center text-[10px] uppercase tracking-widest text-[color:var(--institution-muted)]">
          USFX · Desde 1624
        </div>
      </div>
    </div>
  );
}
