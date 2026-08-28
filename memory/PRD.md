# PRD — Sistema de Comprobantes USFX

## Problem Statement (original)
Aplicación web React + FastAPI + MongoDB con autenticación JWT y 3 roles (admin, caja, consultas) para la **Universidad Mayor, Real y Pontificia de San Francisco Xavier — Facultad de Medicina — Administración**. Migración desde MySQL relacional (SqlComprobantes.sql) a MongoDB. Despliegue listo en Docker.

## Tech & Architecture
- **Backend**: FastAPI (Python 3.11) + Motor (async MongoDB) + PyJWT + bcrypt
- **Frontend**: React 19 + Shadcn UI + Tailwind + react-router-dom 7 + jsPDF + xlsx
- **DB**: MongoDB 7 — Colecciones: users, estudiantes, tipospagos, pagos, counters
- **Auth**: JWT HS256 dual (httpOnly cookie + Bearer header), admin seed automático en startup
- **Deploy**: docker-compose con servicios mongo/backend/frontend

## User Personas
| Rol | Acceso |
|-----|--------|
| Administrador | CRUD Estudiantes, CRUD TiposPagos, CRUD Usuarios, Anular Pago, Reportes, Búsqueda |
| Caja | Registro de pago (con comprobante imprimible), Búsqueda, alta de estudiantes |
| Consultas | Sólo Búsqueda y reimpresión |

## Implemented (2026-05-20)
- ✅ JWT login + seed admin (admin@usfx.edu.bo / admin123)
- ✅ CRUD Estudiantes (codigo, ci, cu, nombre, gestion) — unicidad por código
- ✅ CRUD Tipos de Pago (codigo, nombre, monto, descripcion, inicio, fin)
- ✅ CRUD Usuarios con asignación de rol
- ✅ Registro de Pago: autocompletar estudiante + tipo pago, Generar Comprobante (correlativo NNNNN/YYYY por gestión, atómico via counters collection con $inc), popup nuevo estudiante con re-selección automática, Confirmar e imprimir
- ✅ Comprobante imprimible HTML con encabezado institucional, Cormorant Garamond + IBM Plex Sans, sello ANULADO cuando aplica
- ✅ Búsqueda de Pagos con filtros código (cod/gestion), nombre estudiante, tipo, rango fechas; botón Reimprimir por fila
- ✅ Anular Pago: lista coincidencias, botón Anular inhabilitado tras anulación (auditoría, no se borra)
- ✅ Reportes Diario/Semanal/Mensual/Rango con totales válidos/anulados/diferencia + 3 botones impresión PDF (jsPDF+autoTable) + 3 botones export Excel (xlsx)
- ✅ Diseño Material/Institucional Light mode: cream #FDFBF7 + burgundy #7A2035 + navy #1D3557 + gold #B9975B
- ✅ Docker: Dockerfile.backend, Dockerfile.frontend (multistage nginx), docker-compose.yml, .env.example, .dockerignore
- ✅ README con guía de instalación + quickstart VSCode + API reference + mapeo de migración SQL→Mongo
- ✅ Testing: 35/35 tests backend (pytest) + frontend E2E completo, sin bugs críticos

## Backlog (P1)
- Dashboard con gráficos de tendencias por mes
- Edición de pagos (no sólo anulación) ✅ (2026-05-20 — PUT /api/pagos/{id} admin only, edited_at/edited_by audit)
- Filtro "Registrado por usuario" en Búsqueda y Reportes ✅ (2026-05-20)
- Multi-institución / multi-facultad

## Backlog (P2)
- Lifespan handler en lugar de @app.on_event (deprecation)
- CORS estricto en producción
- secure=True en cookies para HTTPS productivo
- Recuperación de contraseña por email (Resend/SendGrid)
- Logs de auditoría completos (no sólo anulación) — historial por pago
- $lookup agregado en /api/pagos para evitar N+1 ✅ (2026-05-20 — pipeline compartido por /pagos y /reportes + índices id en estudiantes/tipospagos/users)

## Credenciales
- admin@usfx.edu.bo / admin123 (en `/app/memory/test_credentials.md`)
