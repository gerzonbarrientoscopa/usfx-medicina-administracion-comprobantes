# Sistema de Comprobantes — USFX

Aplicación web para emisión, búsqueda, anulación y reporte de comprobantes de pago de la **Universidad Mayor, Real y Pontificia de San Francisco Xavier — Facultad de Medicina — Administración**.

> Stack: **React** + **FastAPI** + **MongoDB**. Autenticación **JWT**. Despliegue listo para **Docker**.

---

## 🗂️ Funcionalidades

### 👤 Roles
| Rol         | Acceso |
|-------------|--------|
| `admin`     | CRUD Estudiantes, CRUD Tipos de Pago, CRUD Usuarios, Anulación de pagos, Reportes, Búsqueda. |
| `caja`      | Registro de pagos (con generación e impresión de comprobante), Búsqueda y reimpresión. |
| `consultas` | Sólo Búsqueda y reimpresión. |

### 📋 Pantallas
- **Login** institucional (split screen).
- **Panel general** con métricas del día.
- **Estudiantes** (Código, CI, CU, Nombre, Gestión).
- **Tipos de Pago** (Código, Nombre, Monto, Descripción, Inicio, Fin).
- **Usuarios** (creación de cuentas para los roles).
- **Anular Pago** (búsqueda por comprobante o nombre; el botón Anular queda inhabilitado tras la anulación).
- **Reportes** (Diario / Semanal / Mensual / Rango) con 3 impresiones:
  - Pagos Válidos (con sumatoria).
  - Pagos Anulados (con sumatoria).
  - Todos los pagos (columnas Válidos / Anulados, sumatoria de cada columna y fila adicional con la diferencia).
  - Exportación a **PDF** (impresión directa) y **Excel** (.xlsx).
- **Registro de Pago** (caja): autocomplete de Estudiante y Tipo de Pago, *popup* para registrar un nuevo estudiante en línea, generación correlativa del código `00001/2026` por gestión, recálculo del total y confirmación con impresión automática del comprobante.
- **Búsqueda de Pagos** con filtros por código (`cod/gestion`), estudiante, tipo y rango de fechas, con botón **Reimprimir** por fila.

### 🧾 Comprobante imprimible
- Encabezado institucional:
  - *Universidad Mayor, Real y Pontificia de San Francisco Xavier*
  - *Facultad de Medicina*
  - *Administración*
- Tipografía Cormorant Garamond + IBM Plex Sans.
- Sello rojo "ANULADO" cuando aplica.

---

## 🐳 Despliegue con Docker

### 1. Requisitos previos
- Docker Desktop o Docker Engine 20+
- docker-compose v2+

### 2. Configuración
Copie `.env.example` a `.env` y edite los valores:

```bash
cp .env.example .env
```

Variables relevantes:
- `JWT_SECRET` — Cadena aleatoria (mínimo 64 caracteres recomendado).
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — Credenciales del admin que se crean en el primer arranque.
- `REACT_APP_BACKEND_URL` — URL pública del backend desde el navegador (en local: `http://localhost:8001`).

### 3. Levantar la aplicación
```bash
docker-compose up --build -d
```

Servicios:
- **Frontend** → http://localhost:3000
- **Backend**  → http://localhost:8001/api
- **MongoDB**  → mongodb://localhost:27017

### 4. Credenciales iniciales
```
Email:    admin@usfx.edu.bo
Password: admin123
```
> Cámbielas en `.env` antes del primer arranque. El admin se crea automáticamente al iniciar el backend.

### 5. Apagar / reiniciar
```bash
docker-compose down          # detener
docker-compose down -v       # detener y borrar datos (mongo volume)
docker-compose logs -f backend
```

---

## 💻 Quickstart en VS Code

### 1. Abrir el proyecto
```bash
git clone <repo>
cd <proyecto>
code .
```

### 2. Extensiones recomendadas
- **Python** (Microsoft)
- **Pylance**
- **ESLint**
- **Prettier**
- **Docker** (Microsoft)
- **MongoDB for VS Code**
- **Tailwind CSS IntelliSense**

### 3. Desarrollo local sin Docker

#### Backend (FastAPI)
```bash
cd backend
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env   # ajustar MONGO_URL si es distinto
uvicorn server:app --reload --host 0.0.0.0 --port 8001
```

> Necesita una instancia de Mongo corriendo. Puede levantar sólo Mongo con:
> ```bash
> docker run -d -p 27017:27017 --name usfx_mongo mongo:7
> ```

#### Frontend (React + craco)
```bash
cd frontend
yarn install
# Asegúrese que .env contenga: REACT_APP_BACKEND_URL=http://localhost:8001
yarn start
```

La app abrirá en http://localhost:3000.

### 4. Tareas integradas (VS Code `tasks.json`)
Puede añadir el siguiente archivo a `.vscode/tasks.json` para arrancar todo con `Ctrl+Shift+B`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Backend",
      "type": "shell",
      "command": "uvicorn server:app --reload --port 8001",
      "options": { "cwd": "${workspaceFolder}/backend" },
      "presentation": { "panel": "new" }
    },
    {
      "label": "Frontend",
      "type": "shell",
      "command": "yarn start",
      "options": { "cwd": "${workspaceFolder}/frontend" },
      "presentation": { "panel": "new" }
    },
    {
      "label": "Dev (backend + frontend)",
      "dependsOn": ["Backend", "Frontend"],
      "group": { "kind": "build", "isDefault": true }
    }
  ]
}
```

---

## 🔌 API Reference (resumen)

Todos los endpoints están prefijados con `/api`. JWT vía cookie `access_token` o header `Authorization: Bearer <token>`.

### Auth
- `POST /api/auth/login` — `{ email, password }` → `{ token, user }`.
- `GET  /api/auth/me`
- `POST /api/auth/logout`

### Estudiantes (admin, caja para crear)
- `GET /api/estudiantes?q=`
- `POST /api/estudiantes`
- `PUT /api/estudiantes/{id}`
- `DELETE /api/estudiantes/{id}`

### Tipos de Pago (admin)
- `GET /api/tipospagos`
- `POST /api/tipospagos`
- `PUT /api/tipospagos/{id}`
- `DELETE /api/tipospagos/{id}`

### Pagos
- `GET /api/pagos/preview-comprobante` — siguiente código `NNNNN/YYYY`.
- `POST /api/pagos` — registra el pago (caja/admin).
- `GET /api/pagos` — filtros `q`, `id_tipopago`, `fecha_desde`, `fecha_hasta`, `incluir_anulados`.
- `POST /api/pagos/{id}/anular` — anula (admin).

### Reportes (admin)
- `GET /api/reportes?periodo=diario|semanal|mensual|rango[&desde&hasta]`

### Usuarios (admin)
- CRUD `/api/users`

---

## 🗃️ Migración desde MySQL

La base de datos original era MySQL relacional (`SqlComprobantes.sql`). La estructura ha sido migrada a colecciones MongoDB:

| MySQL          | MongoDB            | Notas |
|----------------|--------------------|-------|
| `personas`     | `estudiantes`      | Agrega campo `codigo` requerido. |
| `tipospagos`   | `tipospagos`       | Nuevo campo `codigo`. |
| `pagos`        | `pagos`            | Nuevos campos: `total`, `anulado`, `anulado_at`, `anulado_by`, `created_by`. |
| (auto-incr)    | `counters`         | Mantiene el correlativo por gestión `comprobante_YYYY`. |
| —              | `users`            | Autenticación JWT. |

El correlativo del comprobante usa `findOneAndUpdate` con `$inc` (atómico) sobre la colección `counters`, garantizando códigos consecutivos por gestión.

---

## 🧪 Testing

- Backend: `pytest` (instalado en `requirements.txt`).
- Lint: `ruff` / `eslint`.
- Smoke test rápido con `curl`:

```bash
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@usfx.edu.bo","password":"admin123"}'
```

---

## 📝 Licencia

Uso institucional — Universidad Mayor, Real y Pontificia de San Francisco Xavier — Facultad de Medicina.
