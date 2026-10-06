# Pruebas de integración para SQL Server local

Esta suite opt-in instala y prueba el DDL real de `backend/Tablas.Sql` y las
rutas de `backend/serverSQL.py`. Ejecútala **solo en tu equipo**, contra una
base de datos de prueba nueva. No ejecuta, limpia ni elimina `ComprobantesDB`.
Los registros de prueba permanecen en la base seleccionada.

## Requisitos

- Python y las dependencias de `backend/requirements-sql.txt`.
- Microsoft ODBC Driver 18 for SQL Server.
- Un SQL Server local al que tu usuario pueda conectarse y crear bases.
- Un nombre de base nuevo que comience con `USFX_TEST_`.

El instalador exige `RUN_SQLSERVER_LOCAL_INTEGRATION=1`, un nombre de base
explícito, y rechaza una base que ya exista. La suite comprueba el nombre de la
base efectiva y una marca que escribe el instalador **antes** de iniciar la API.
No configura `.env`; desactiva su lectura para esta ejecución y usa claves
temporales exclusivas para el administrador de prueba.

## Windows PowerShell

Desde la carpeta raíz del proyecto, selecciona un nombre nuevo cada vez:

```powershell
py -m pip install -r backend\requirements-sql.txt

$env:SQLSERVER_HOST = ".\SQLEXPRESS" # reemplaza por tu instancia local
$env:SQLSERVER_DATABASE = "USFX_TEST_20261005_01" # elige un nombre nuevo
$env:RUN_SQLSERVER_LOCAL_INTEGRATION = "1"
Remove-Item Env:SQLSERVER_CONNECTION_STRING -ErrorAction SilentlyContinue

# Elige una autenticación:
$env:SQLSERVER_TRUSTED_AUTH = "1" # Windows Authentication
# O usa SQL Server Authentication; sustituye estos valores solo localmente:
# $env:SQLSERVER_TRUSTED_AUTH = "0"
# $env:SQLSERVER_USER = "tu_usuario_local"
# $env:SQLSERVER_PASSWORD = "tu_contraseña_local"

py backend\tests\sqlserver_local\prepare_db.py --database $env:SQLSERVER_DATABASE
py -m pytest -q backend\tests\test_sqlserver_local_integration.py
```

No compartas la contraseña en el chat ni la guardes en el repositorio.

## Linux o macOS

Instala el controlador ODBC 18 para tu sistema y las dependencias Python. Luego,
en la misma terminal donde prepararás y ejecutarás las pruebas:

```bash
python -m pip install -r backend/requirements-sql.txt
export SQLSERVER_HOST='localhost' # instancia SQL Server local
export SQLSERVER_DATABASE='USFX_TEST_20261005_01' # elige un nombre nuevo
export SQLSERVER_TRUSTED_AUTH='0'
export SQLSERVER_USER='tu_usuario_local'
export SQLSERVER_PASSWORD='tu_contraseña_local'
export RUN_SQLSERVER_LOCAL_INTEGRATION='1'
unset SQLSERVER_CONNECTION_STRING

python backend/tests/sqlserver_local/prepare_db.py --database "$SQLSERVER_DATABASE"
python -m pytest -q backend/tests/test_sqlserver_local_integration.py
```

## Qué comprueba

- El DDL instalado realmente: columnas `INT IDENTITY`, clave `CHAR(3)`, índices
  únicos de comprobantes y rechazo de códigos de usuario inválidos.
- Altas reales y CRUD por roles y oficina, incluida la prohibición de cruzar
  oficinas o cambiar el código asignado a un usuario.
- Secuencia compartida entre pagos y alquileres; pagar una reserva repetidamente
  no emite otro comprobante.
- Reservas simultáneas del mismo horario: una se confirma y la otra recibe
  conflicto.
- Anulación de pagos y alquileres, y ausencia de `comprobante_display` como
  columna persistida (aunque la API lo calcule para las respuestas).

La suite requiere una base preparada por `prepare_db.py`; no uses una base con
datos reales ni vuelvas a ejecutar la preparación sobre una base existente. Si
una instalación falla a mitad, el instalador conserva esa base para inspección
y no intenta borrarla.

Las pruebas offline existentes pueden seguir ejecutándose sin SQL Server:

```bash
python -m pytest -q backend/tests/test_sql_schema_contract.py
```
