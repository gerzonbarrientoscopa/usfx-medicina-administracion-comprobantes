#!/bin/sh
set -eu

export SQLSERVER_HOST="${SQLSERVER_HOST:-sqlserver,1433}"
export SQLSERVER_DATABASE="${SQLSERVER_DATABASE:-ComprobantesDB}"
export SQLSERVER_USER="${SQLSERVER_USER:-usrweb_comprobantes}"
export SQLSERVER_TRUSTED_AUTH="${SQLSERVER_TRUSTED_AUTH:-0}"
if [ -z "${SQLSERVER_DRIVER:-}" ]; then
  export SQLSERVER_DRIVER='{ODBC Driver 17 for SQL Server}'
fi

if [ -z "${JWT_SECRET:-}" ]; then
  export JWT_SECRET="${SESSION_SECRET:-}"
fi

: "${JWT_SECRET:?Define JWT_SECRET o SESSION_SECRET}"
: "${ADMIN_PASSWORD:?Define ADMIN_PASSWORD}"

if [ -z "${SQLSERVER_CONNECTION_STRING:-}" ]; then
  : "${SQLSERVER_PASSWORD:?Define SQLSERVER_PASSWORD con la contraseña de usrweb_comprobantes}"
fi

python - <<'PY'
import os
import sys
import time

import pyodbc


def quote_odbc(value):
    return "{" + str(value).replace("}", "}}") + "}"


connection_string = os.getenv("SQLSERVER_CONNECTION_STRING")
if not connection_string:
    server = os.environ["SQLSERVER_HOST"]
    database = quote_odbc(os.environ["SQLSERVER_DATABASE"])
    user = quote_odbc(os.environ["SQLSERVER_USER"])
    password = quote_odbc(os.environ["SQLSERVER_PASSWORD"])
    driver = os.environ["SQLSERVER_DRIVER"]
    connection_string = (
        f"DRIVER={driver};"
        f"SERVER={server};DATABASE={database};UID={user};PWD={password};"
        "Encrypt=no;TrustServerCertificate=yes;Connection Timeout=5;"
    )

driver_description = (
    "la cadena SQLSERVER_CONNECTION_STRING"
    if connection_string
    else f"el controlador {os.environ['SQLSERVER_DRIVER']}"
)
print(
    f"Esperando SQL Server en {os.environ['SQLSERVER_HOST']} "
    f"y la base {os.environ['SQLSERVER_DATABASE']} usando {driver_description}.",
    flush=True,
)
for attempt in range(60):
    try:
        connection = pyodbc.connect(connection_string, timeout=5)
        connection.cursor().execute("SELECT 1").fetchone()
        connection.close()
        break
    except pyodbc.Error:
        if attempt == 59:
            print(
                "No se pudo conectar a SQL Server. Verifica el servicio, "
                "el esquema de Tablas.Sql y las credenciales.",
                file=sys.stderr,
                flush=True,
            )
            raise
        time.sleep(2)
PY

exec uvicorn serverSQL2012:app --host 0.0.0.0 --port 8000
