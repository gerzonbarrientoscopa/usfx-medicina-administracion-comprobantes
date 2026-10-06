"""Static SQL source/schema inspection only: no backend code is executed."""
import ast
import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "serverSQL.py"
TEXT = SOURCE.read_text()
TREE = ast.parse(TEXT)
SCHEMA = SOURCE.with_name("Tablas.Sql").read_text()


def test_schema_identity_keys_and_separate_user_code():
    for table in ("oficinas", "usuarios", "clientes", "tipos_pagos", "ambientes",
                  "tarifas_ambientes", "pagos", "pago_items", "alquileres",
                  "alquiler_intervalos", "ocupacion_intervalos", "ambiente_horarios"):
        body = SCHEMA.split(f"CREATE TABLE dbo.{table} (", 1)[1].split(");", 1)[0]
        assert re.search(r"\bid int IDENTITY\(1,1\)", body), table
    users = SCHEMA.split("CREATE TABLE dbo.usuarios (", 1)[1].split(");", 1)[0]
    assert "codigo char(3)" in users and "UQ_usuarios_codigo UNIQUE" in users
    assert "LIKE '[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]'" in users
    assert "CREATE TABLE dbo.estudiantes" not in SCHEMA
    assert "CREATE TABLE dbo.personas" not in SCHEMA


def test_schema_clients_and_receipt_foreign_keys():
    assert "IX_clientes_ci ON dbo.clientes(ci_key) WHERE ci<>N''" in SCHEMA
    assert "IX_clientes_cu ON dbo.clientes(cu_key) WHERE cu<>N''" in SCHEMA
    assert SCHEMA.count("FOREIGN KEY(id_cliente) REFERENCES dbo.clientes(id)") == 2
    assert "tipo_cliente" not in SCHEMA and "cliente_documento" not in SCHEMA
    assert "created_by int" in SCHEMA and "registrado_por int" in SCHEMA


def test_sql_json_mapping_and_string_identifiers():
    mapping = next(n.value for n in TREE.body if isinstance(n, ast.Assign)
                   and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "_SQL_COLUMNS")
    values = ast.literal_eval(mapping)
    assert values["cliente_id"] == "id_cliente"
    assert values["cliente_nombre"] == "nombre_cliente"
    assert "cliente_tipo" not in values
    assert "str(value) if isinstance(value, int)" in TEXT
    assert "id AS codigo" not in TEXT


def test_user_crud_restricted_and_generated_sql_id():
    for name in ("users", "create_user", "update_user", "delete_user", "users_admin_list"):
        node = next(n for n in TREE.body if getattr(n, "name", None) == name)
        code = ast.get_source_segment(TEXT, node)
        assert 'roles("SuperAdmin")' in code, name
    create = next(n for n in TREE.body if getattr(n, "name", None) == "create_user")
    code = ast.get_source_segment(TEXT, create)
    assert "INSERT INTO usuarios(codigo,email" in code
    assert "OUTPUT INSERTED.id" in code and "INSERT INTO usuarios(id," not in TEXT


def test_rental_insert_placeholder_contract_and_occupancy_protection():
    insert = next(n for n in ast.walk(TREE) if isinstance(n, ast.Call)
                  and n.args and isinstance(n.args[0], ast.Constant)
                  and isinstance(n.args[0].value, str)
                  and n.args[0].value.startswith("INSERT INTO alquileres("))
    assert insert.args[0].value.count("?") == len(insert.args[1].elts)
    assert "cliente_tipo" not in insert.args[0].value
    assert "cliente_id" in insert.args[0].value
    assert "sp_getapplock" in TEXT and "UPDLOCK,HOLDLOCK" in TEXT
    assert "b.cliente_documento" not in TEXT and "s.office_id=p.office_id" not in TEXT


def test_single_router_installation_and_shared_clients_routes():
    assert TEXT.count("app.include_router(api)") == 1
    assert "SQLClientes(sql)" in TEXT and "register_client_routes" in TEXT
    assert '"clientes",' in TEXT[TEXT.index("async def reconcile_startup"):]
    assert "/estudiantes" not in TEXT and "/personas" not in TEXT
