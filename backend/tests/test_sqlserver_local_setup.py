"""Offline checks for the local SQL Server test-database safety gate."""

from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest


SETUP_PATH = (
    Path(__file__).resolve().parent / "sqlserver_local" / "prepare_db.py"
)
SETUP = runpy.run_path(str(SETUP_PATH))


def test_database_name_requires_a_new_test_prefix():
    assert SETUP["_selected_database"]("USFX_TEST_20261005_01") == (
        "USFX_TEST_20261005_01"
    )
    for value in (
        "ComprobantesDB",
        "USFX_TEST_data; SELECT 1",
        "USFX_TEST_bad-name",
        "test_database",
    ):
        with pytest.raises(SystemExit):
            SETUP["_selected_database"](value)


def test_real_schema_script_targets_only_the_selected_test_database():
    database = "USFX_TEST_STATIC_1"
    ddl = SETUP["_database_ddl"](database)

    assert f"IF DB_ID(N'{database}') IS NULL" in ddl
    assert f"CREATE DATABASE [{database}];" in ddl
    assert f"USE [{database}];" in ddl
    assert "CREATE DATABASE ComprobantesDB;" not in ddl
    assert "USE ComprobantesDB;" not in ddl
    assert len(list(SETUP["_batches"](ddl))) >= 5


def test_database_creation_requires_an_explicit_local_opt_in(monkeypatch):
    monkeypatch.delenv("RUN_SQLSERVER_LOCAL_INTEGRATION", raising=False)
    with pytest.raises(SystemExit, match="RUN_SQLSERVER_LOCAL_INTEGRATION"):
        SETUP["_environment"]("USFX_TEST_STATIC_1")

    monkeypatch.setenv("RUN_SQLSERVER_LOCAL_INTEGRATION", "1")
    monkeypatch.setenv("SQLSERVER_DATABASE", "USFX_TEST_STATIC_1")
    monkeypatch.setenv("SQLSERVER_HOST", r".\SQLEXPRESS")
    monkeypatch.setenv("SQLSERVER_TRUSTED_AUTH", "1")
    monkeypatch.delenv("SQLSERVER_CONNECTION_STRING", raising=False)

    connection, host = SETUP["_environment"]("USFX_TEST_STATIC_1")
    assert host == r".\SQLEXPRESS"
    assert "DATABASE={master}" in connection
    assert "Trusted_Connection=yes" in connection

    monkeypatch.setenv("SQLSERVER_CONNECTION_STRING", "not-used-here")
    with pytest.raises(SystemExit):
        SETUP["_environment"]("USFX_TEST_STATIC_1")


def test_installer_refuses_existing_database_before_running_any_ddl(monkeypatch):
    statements = []

    class Cursor:
        def execute(self, statement, params=()):
            statements.append(statement)
            return self

        def fetchone(self):
            return ("USFX_TEST_ALREADY_EXISTS",)

        def close(self):
            pass

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setenv("RUN_SQLSERVER_LOCAL_INTEGRATION", "1")
    monkeypatch.setenv("SQLSERVER_DATABASE", "USFX_TEST_ALREADY_EXISTS")
    monkeypatch.setenv("SQLSERVER_HOST", r".\SQLEXPRESS")
    monkeypatch.setenv("SQLSERVER_TRUSTED_AUTH", "1")
    monkeypatch.delenv("SQLSERVER_CONNECTION_STRING", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "pyodbc",
        SimpleNamespace(connect=lambda *args, **kwargs: Connection()),
    )

    with pytest.raises(SystemExit, match="ya existe"):
        SETUP["install"]("USFX_TEST_ALREADY_EXISTS")
    assert statements == ["SELECT name FROM sys.databases WHERE name=?"]
