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

### 4. Credenciales administrativas
Configura `ADMIN_EMAIL`, `ADMIN_PASSWORD` y `ADMIN_NAME` como secretos
privados antes del primer arranque. No se proporcionan credenciales
administrativas predeterminadas. El admin se crea o actualiza automáticamente
al iniciar el backend.

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

### Clientes (SuperAdmin, Administrador y Caja)
- `GET /api/clientes?textoBuscar=` — catálogo compartido, paginado.
- `POST /api/clientes` — `{ ci, cu, nombre }`; Id generado en backend.
- `PUT /api/clientes/{id}`
- `DELETE /api/clientes/{id}` — bloqueado si tiene pagos o alquileres.
- `GET /api/clientes/importacion?q=` — consultar servicio externo y seleccionar un registro.

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

### Usuarios (solo SuperAdmin)
- CRUD `/api/usuarios`; Código separado del Id generado.
- `GET /api/usuarios/importacion?q=` — consulta del directorio configurable.
- `GET /api/reportes/registradores` — nombres/Ids para filtrar reportes dentro de la oficina; no administración de usuarios.

---

## Inicio desde cero e importación

No se migran los catálogos anteriores de Estudiantes y Personas. Ambos backends
utilizan Clientes con Id generado, C.I., C.U. y Nombre completo. Al menos un
C.I. o C.U. debe existir; cada identificador no vacío es único en todo el catálogo.
MongoDB genera UUIDs; SQL Server utiliza INT IDENTITY. El frontend trata todos
los Id como cadenas. Los pagos y alquileres envían cliente_id.

### SQL Server local

Mantenga juntos los archivos del directorio backend (incluidos client_models.py,
client_routes.py e import_services.py); instale requirements-sql.txt en su equipo.
Detenga serverSQL.py. Para **borrar todos los datos locales** de ComprobantesDB,
ejecute backend/ReiniciarLocal.Sql (destructivo); luego backend/Tablas.Sql e inicie
serverSQL.py. El inicio crea únicamente el SuperAdmin de las variables ADMIN_*.
Tablas.Sql no borra bases existentes y rechaza esquemas incompatibles.
Si usa otro nombre de base, ajuste ambos scripts y SQLSERVER_DATABASE.
Nunca se conecta ni ejecuta serverSQL.py desde Replit.

### Directorios externos

Configure CLIENTS_IMPORT_API_URL y USERS_IMPORT_API_URL en el entorno del
backend; opcionalmente CLIENTS_IMPORT_API_TOKEN / USERS_IMPORT_API_TOKEN para
Bearer. No ponga tokens en variables REACT_APP_* ni en el frontend.
Cada URL se consulta mediante GET y devuelve una lista JSON:

- Clientes: [{"CI":"123", "CU":"456", "Nombre Completo":"Nombre Apellido"}]
- Usuarios: [{"Código":"007", "Nombre Completo":"Nombre Apellido", "Email":"persona@example.com"}]

Se aceptan también las claves canónicas ci/cu/nombre y codigo/nombre/email.
Los Id externos se descartan. En “Importar desde API” seleccione un resultado,
revise el formulario y confirme; los usuarios requieren además contraseña,
rol y oficina. No se crean registros automáticamente al consultar el servicio.
Servicios ausentes, inaccesibles o con formato inválido muestran errores explícitos.
Sincronización masiva/automática no forma parte de esta importación seleccionable.

----------------|--------------------|-------|
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
  -d '{"email":"TU_ADMIN_EMAIL","password":"TU_ADMIN_PASSWORD"}'
```

---

## 📝 Licencia

Uso institucional — Universidad Mayor, Real y Pontificia de San Francisco Xavier — Facultad de Medicina.
