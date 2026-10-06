"""Create and install the SQL schema in a new, explicitly named local test DB.

This script is intentionally separate from serverSQL.py. It refuses an existing
database and never drops or modifies an existing database.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


DATABASE_NAME = re.compile(r"USFX_TEST_[A-Za-z0-9_]{1,110}\Z")
GO_LINE = re.compile(r"^\s*GO\s*(?:--.*)?$", re.IGNORECASE | re.MULTILINE)
DDL_PATH = Path(__file__).resolve().parents[2] / "Tablas.Sql"
GUARD_TABLE = "dbo.__local_sqlserver_test_guard"
GUARD_PURPOSE = "local SQL Server integration tests"


def _selected_database(value: str) -> str:
    if not DATABASE_NAME.fullmatch(value):
        raise SystemExit(
            "El nombre debe comenzar con USFX_TEST_ y contener solo letras, "
            "números y guion bajo."
        )
    if value.casefold() == "comprobantesdb":
        raise SystemExit("ComprobantesDB no es una base de pruebas permitida.")
    return value


def _environment(database: str) -> tuple[str, str]:
    if os.environ.get("RUN_SQLSERVER_LOCAL_INTEGRATION") != "1":
        raise SystemExit(
            "Confirma la ejecución local configurando "
            "RUN_SQLSERVER_LOCAL_INTEGRATION=1."
        )
    if os.environ.get("SQLSERVER_DATABASE") != database:
        raise SystemExit(
            "--database debe coincidir exactamente con SQLSERVER_DATABASE."
        )
    if os.environ.get("SQLSERVER_CONNECTION_STRING"):
        raise SystemExit(
            "Para este instalador, quita SQLSERVER_CONNECTION_STRING y configura "
            "SQLSERVER_HOST más SQLSERVER_DATABASE."
        )

    host = os.environ.get("SQLSERVER_HOST", "").strip()
    if not host:
        raise SystemExit("Configura explícitamente SQLSERVER_HOST para tu SQL Server local.")

    driver = "ODBC Driver 18 for SQL Server"

    def escaped(value: str) -> str:
        return "{" + value.replace("}", "}}") + "}"

    connection = (
        f"DRIVER={escaped(driver)};SERVER={escaped(host)};"
        "DATABASE={master};Encrypt=yes;TrustServerCertificate=yes;"
    )
    trusted = os.environ.get("SQLSERVER_TRUSTED_AUTH", "").strip().lower()
    if trusted in {"1", "true", "yes"}:
        connection += "Trusted_Connection=yes;"
    else:
        username = os.environ.get("SQLSERVER_USER", "")
        password = os.environ.get("SQLSERVER_PASSWORD", "")
        if not username or not password:
            raise SystemExit(
                "Configura SQLSERVER_TRUSTED_AUTH=1 o las variables locales "
                "SQLSERVER_USER y SQLSERVER_PASSWORD."
            )
        connection += f"UID={escaped(username)};PWD={escaped(password)};"
    return connection, host


def _database_ddl(database: str) -> str:
    try:
        source = DDL_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"No se pudo leer el DDL existente: {DDL_PATH}") from exc

    create_header = "IF DB_ID(N'ComprobantesDB') IS NULL"
    create_statement = "CREATE DATABASE ComprobantesDB;"
    use_header = "USE ComprobantesDB;"
    if (
        source.count(create_header) != 1
        or source.count(create_statement) != 1
        or source.count(use_header) != 1
    ):
        raise SystemExit(
            "El encabezado de backend/Tablas.Sql cambió; revisa el instalador "
            "antes de preparar otra base."
        )
    return source.replace(
        create_header, f"IF DB_ID(N'{database}') IS NULL", 1
    ).replace(
        create_statement, f"CREATE DATABASE [{database}];", 1
    ).replace(use_header, f"USE [{database}];", 1)


def _batches(script: str):
    for batch in GO_LINE.split(script):
        if batch.strip():
            yield batch


def install(database: str) -> None:
    connection_string, host = _environment(database)
    script = _database_ddl(database)
    try:
        import pyodbc
    except ImportError as exc:
        raise SystemExit(
            "Falta pyodbc. Instala backend/requirements-sql.txt y el controlador "
            "ODBC Driver 18 for SQL Server."
        ) from exc

    connection = None
    cursor = None
    created = False
    try:
        connection = pyodbc.connect(connection_string, autocommit=True)
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM sys.databases WHERE name=?", (database,))
        if cursor.fetchone():
            raise SystemExit(
                f"La base {database!r} ya existe en {host}. No se reutiliza ni se borra; "
                "elige otro nombre de prueba nuevo."
            )

        # The identifier is built only after strict allow-list validation.
        cursor.execute(f"CREATE DATABASE [{database}]")
        created = True

        for batch in _batches(script):
            cursor.execute(batch)

        cursor.execute(
            f"""CREATE TABLE {GUARD_TABLE} (
                    database_name sysname NOT NULL,
                    purpose nvarchar(80) NOT NULL,
                    state varchar(16) NOT NULL
                        CONSTRAINT CK_local_sqlserver_test_state
                        CHECK(state IN ('prepared','running'))
                );
                INSERT INTO {GUARD_TABLE}(database_name,purpose,state)
                    VALUES(DB_NAME(), N'{GUARD_PURPOSE}', 'prepared');"""
        )
    except SystemExit:
        raise
    except Exception as exc:
        if created:
            raise SystemExit(
                f"No se pudo terminar la instalación de {database!r}. La base se "
                "conservó para inspección; no la uses hasta resolver el error. "
                "Elige otro nombre nuevo para volver a preparar una base vacía."
            ) from exc
        raise SystemExit(
            f"No se pudo conectar a {host!r} o consultar la lista de bases. "
            "Verifica el servidor y los permisos locales."
        ) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    print(f"DDL instalado en la base nueva {database!r} de {host!r}.")
    print("La base queda conservada al terminar las pruebas; no se elimina nada.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Instala backend/Tablas.Sql en una base local nueva de pruebas."
    )
    parser.add_argument(
        "--database",
        required=True,
        help="Nombre nuevo USFX_TEST_...; también debe estar en SQLSERVER_DATABASE.",
    )
    args = parser.parse_args()
    install(_selected_database(args.database))


if __name__ == "__main__":
    main()
