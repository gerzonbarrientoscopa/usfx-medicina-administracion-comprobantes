"""Offline SQL contract checks. Never import the backend or connect to SQL Server."""
import ast
import asyncio
import copy
import re
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "serverSQL.py"
SCHEMA = SOURCE.with_name("Tablas.Sql").read_text()
TREE = ast.parse(SOURCE.read_text())


def offline_definitions(*names):
    """Extract only requested definitions; no imports, app, secrets or startup."""
    nodes = []
    for original in TREE.body:
        name = getattr(original, "name", None)
        if isinstance(original, ast.Assign):
            name = getattr(original.targets[0], "id", None)
        if name not in names:
            continue
        node = copy.deepcopy(original)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.decorator_list = []
            node.args.defaults = [ast.Constant(None) for _ in node.args.defaults]
        nodes.append(node)
    namespace = {
        "re": re, "datetime": datetime, "timezone": timezone,
        "Decimal": Decimal, "ROUND_HALF_UP": ROUND_HALF_UP,
        "PagoCreate": object,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 str(SOURCE), "exec"), namespace)
    return namespace


@pytest.fixture
def adapter():
    return offline_definitions(
        "_SQL_COLUMNS", "_API_COLUMNS", "_SQL_IDENTIFIER", "_ID_COLUMNS",
        "_physical_sql", "_SQLCursor", "_SQLConnection", "_rows",
    )


def test_schema_uses_numeric_identity_and_manual_user_primary_key():
    for table in ("oficinas", "personas", "estudiantes", "tipos_pagos",
                  "ambientes", "tarifas_ambientes", "pagos", "pago_items",
                  "alquileres", "alquiler_intervalos", "ocupacion_intervalos",
                  "ambiente_horarios"):
        body = SCHEMA.split(f"CREATE TABLE dbo.{table} ", 1)[1].split(";", 1)[0]
        assert re.search(r"\bid int IDENTITY\(1,1\)", body), table
    assert "id char(3) NOT NULL CONSTRAINT PK_usuarios PRIMARY KEY" in SCHEMA
    assert "CK_usuarios_codigo" in SCHEMA and "CK_usuarios_superadmin" in SCHEMA
    assert "origen_id int NOT NULL" in SCHEMA
    assert "DROP DATABASE" not in SCHEMA


def test_schema_has_new_columns_and_only_live_sql_process_fields(adapter):
    for old, new in adapter["_SQL_COLUMNS"].items():
        assert not re.search(r"\b" + old + r"\b", SCHEMA), old
        assert re.search(r"\b" + new + r"\b", SCHEMA), new
    for unused in ("comprobante_display", "alquiler_arrendamientos",
                   "processing_started_at", "payment_token", "processing_lease_until"):
        assert unused not in SCHEMA
    assert "confirmation_started_at datetime2" in SCHEMA
    assert "uuid.uuid4" not in SOURCE.read_text()


def test_all_generated_identity_inserts_request_inserted_id():
    tables = {"oficinas", "estudiantes", "personas", "tipos_pagos", "ambientes",
              "tarifas_ambientes", "pagos", "alquileres"}
    found = set()
    for node in ast.walk(TREE):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            match = re.match(r"\s*INSERT INTO (\w+)\(", node.value, re.I)
            if match and match.group(1) in tables:
                found.add(match.group(1))
                assert "OUTPUT INSERTED.id" in node.value
                columns = node.value.split("(", 1)[1].split(")", 1)[0].split(",")
                assert "id" not in [c.strip() for c in columns]
    assert found == tables


def test_adapter_translates_sql_not_literals_and_preserves_json_id_types(adapter):
    statement = "SELECT office_id,cliente_nombre FROM alquiler_tramos WHERE paid_by=? AND cliente_tipo=N'persona'"
    translated = adapter["_physical_sql"](statement)
    assert translated == "SELECT id_oficina,nombre_cliente FROM alquiler_intervalos WHERE registrado_por=? AND tipo_cliente=N'persona'"
    assert adapter["_physical_sql"]("SELECT 'office_id' AS office_id -- paid_by") == "SELECT 'office_id' AS id_oficina -- paid_by"
    raw = SimpleNamespace(
        description=[("id",), ("id_oficina",), ("id_ambiente",), ("total",), ("nombre_cliente",)],
        fetchall=lambda: [(42, 7, 8, Decimal("12.50"), "Cliente")],
    )
    rows = adapter["_rows"](adapter["_SQLCursor"](raw))
    assert rows == [{"id": "42", "office_id": "7", "ambiente_id": "8",
                     "total": Decimal("12.50"), "cliente_nombre": "Cliente"}]


@pytest.mark.parametrize("with_item", [False, True])
def test_payment_identity_is_allocated_before_shared_receipt(adapter, with_item):
    namespace = offline_definitions("create_payment")
    calls = []
    state = {}

    class Cursor:
        def execute(self, statement, params=()):
            assert statement.count("?") == len(params)
            calls.append((statement, params))
            if statement.startswith("SELECT id FROM estudiantes"):
                self.description, self.row = [("id",)], (5,)
            elif statement.startswith("SELECT nombre,monto"):
                self.description, self.row = [("nombre",), ("monto",)], ("Concepto", Decimal("10"))
            elif "INSERT INTO pagos(" in statement:
                state["inserted"] = True
                self.description, self.row = [("id",)], (42,)
            return self

        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def cursor(self):
            return Cursor()

        def commit(self):
            state["committed"] = True

    async def office(*args):
        return "7"

    async def tx(fn):
        return fn()

    async def sql(statement, params, **kwargs):
        assert params == ("42",)
        return {"id": "42"}

    async def hydrate(row):
        return row

    def allocate(cursor, oid, year, origin, ident):
        assert state["inserted"] and ident == "42" and oid == "7" and origin == "pago"
        return "00001", "ABC"

    namespace.update(
        office=office, tx=tx, sql=sql, hydrate_payment=hydrate,
        allocate_receipt=allocate, parse_iso_date=date.fromisoformat,
        _connect=lambda: adapter["_SQLConnection"](Connection()),
    )
    body = SimpleNamespace(
        office_id="7", id_estudiante="5", fecha_pago="2026-10-05",
        id_tipo_pago="3" if with_item else None, cantidad=2 if with_item else None,
    )
    assert asyncio.run(namespace["create_payment"](body, {"id": "007"})) == {"id": "42"}
    assert state["committed"]
    assert any("UPDATE pagos SET cod_comprobante=" in query for query, _ in calls)
    items = [(query, params) for query, params in calls if "INSERT INTO pago_items" in query]
    assert bool(items) is with_item
    if with_item:
        assert items[0][1] == ("42", "3", "Concepto", Decimal("2"), Decimal("10"), Decimal("20.00"))
        assert "id_pago" in items[0][0]
