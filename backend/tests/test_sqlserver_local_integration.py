"""Opt-in integration tests that exercise the real SQL Server DDL and API.

Do not run this suite from Replit. It imports serverSQL and writes test records
to the explicitly selected, locally prepared USFX_TEST_* database.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest


if os.environ.get("RUN_SQLSERVER_LOCAL_INTEGRATION") != "1":
    pytest.skip(
        "Suite local opt-in: configura RUN_SQLSERVER_LOCAL_INTEGRATION=1 "
        "y sigue backend/tests/sqlserver_local/README.md.",
        allow_module_level=True,
    )


DATABASE_PATTERN = re.compile(r"USFX_TEST_[A-Za-z0-9_]{1,110}\Z")
BACKEND = Path(__file__).resolve().parents[1]
API = "/api"
TEST_ADMIN_EMAIL = "sql-local-integration-admin@example.com"
TEST_PASSWORD = "sql-local-integration-only-password"


def _local_configuration():
    database = os.environ.get("SQLSERVER_DATABASE", "")
    if not DATABASE_PATTERN.fullmatch(database):
        pytest.fail(
            "SQLSERVER_DATABASE debe ser el nombre nuevo USFX_TEST_... "
            "instalado con prepare_db.py."
        )
    if not os.environ.get("SQLSERVER_HOST", "").strip():
        pytest.fail("SQLSERVER_HOST debe indicar explícitamente el SQL Server local.")
    if os.environ.get("SQLSERVER_CONNECTION_STRING"):
        pytest.fail(
            "Quita SQLSERVER_CONNECTION_STRING para esta suite y configura "
            "SQLSERVER_HOST, SQLSERVER_DATABASE y la autenticación local."
        )
    trusted = os.environ.get("SQLSERVER_TRUSTED_AUTH", "").strip().lower()
    if trusted not in {"1", "true", "yes"} and not (
        os.environ.get("SQLSERVER_USER") and os.environ.get("SQLSERVER_PASSWORD")
    ):
        pytest.fail(
            "Configura SQLSERVER_TRUSTED_AUTH=1 o SQLSERVER_USER y "
            "SQLSERVER_PASSWORD en tu entorno local."
        )
    return database


def _import_local_backend():
    # Isolate the app from any .env file: startup receives test-only auth values,
    # and all SQL target settings must be supplied explicitly in this shell.
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["JWT_SECRET"] = "local-sql-integration-jwt-secret-only"
    os.environ["SESSION_SECRET"] = "local-sql-integration-session-secret-only"
    os.environ["ADMIN_EMAIL"] = TEST_ADMIN_EMAIL
    os.environ["ADMIN_PASSWORD"] = TEST_PASSWORD
    os.environ["ADMIN_NAME"] = "SQL local integration test"

    module_name = "_usfx_server_sql_local_integration"
    spec = importlib.util.spec_from_file_location(module_name, BACKEND / "serverSQL.py")
    if spec is None or spec.loader is None:
        pytest.fail("No se pudo cargar backend/serverSQL.py en el equipo local.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _read_rows(module, statement, params=()):
    connection = module.pyodbc.connect(module._connection_string(), autocommit=True)
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(statement, tuple(params))
            return [tuple(row) for row in cursor.fetchall()]
        finally:
            cursor.close()
    finally:
        connection.close()


def _login(client, email, password=TEST_PASSWORD):
    response = client.post(
        f"{API}/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _monday_after(weeks: int = 0) -> str:
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    return (today + timedelta(days=days_until_monday + weeks * 7)).isoformat()


def _office_payload(name, prefix):
    return {
        "nombre": name,
        "prefijo_comprobante": prefix,
        "suboficina": "Pruebas locales",
        "activa": True,
    }


def _create_user(client, headers, code, email, role, office_id):
    response = client.post(
        f"{API}/usuarios",
        headers=headers,
        json={
            "codigo": code,
            "email": email,
            "nombre": f"Usuario {code}",
            "password": TEST_PASSWORD,
            "rol": role,
            "office_id": office_id,
        },
    )
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["id"] == code
    assert row["codigo"] == code
    return row


@pytest.fixture(scope="module")
def local_sql():
    database = _local_configuration()
    module = _import_local_backend()

    # This is a read-only identity/marker check before TestClient triggers
    # startup reconciliation or seeds its test administrator.
    try:
        identity = _read_rows(module, "SELECT DB_NAME()")
        guard = _read_rows(
            module,
            """SELECT database_name,purpose,state FROM dbo.__local_sqlserver_test_guard
               WHERE database_name=DB_NAME()""",
        )
    except Exception as exc:
        pytest.fail(
            "No se pudo comprobar la base local preparada. Ejecuta primero "
            "prepare_db.py contra una base nueva y verifica la conexión local. "
            f"Error de conexión/guardia: {exc}"
        )
    assert identity and identity[0][0] == database, (
        "La conexión efectiva del backend apunta a otra base; no se iniciará la API."
    )
    assert guard and guard[0][0] == database and guard[0][1] == (
        "local SQL Server integration tests"
    ) and guard[0][2] == "prepared", (
        "Falta la marca creada por prepare_db.py; no se iniciará la API."
    )

    empty_domain = _read_rows(
        module,
        """SELECT
             (SELECT COUNT_BIG(*) FROM dbo.oficinas) +
             (SELECT COUNT_BIG(*) FROM dbo.usuarios) +
             (SELECT COUNT_BIG(*) FROM dbo.personas) +
             (SELECT COUNT_BIG(*) FROM dbo.estudiantes) +
             (SELECT COUNT_BIG(*) FROM dbo.tipos_pagos) +
             (SELECT COUNT_BIG(*) FROM dbo.ambientes) +
             (SELECT COUNT_BIG(*) FROM dbo.pagos) +
             (SELECT COUNT_BIG(*) FROM dbo.alquileres)""",
    )
    assert empty_domain and empty_domain[0][0] == 0, (
        "La base seleccionada ya tiene datos de aplicación; no se iniciará la API."
    )

    claim = module.pyodbc.connect(module._connection_string(), autocommit=False)
    try:
        cursor = claim.cursor()
        cursor.execute(
            """UPDATE dbo.__local_sqlserver_test_guard SET state='running'
               WHERE database_name=DB_NAME()
                 AND purpose=? AND state='prepared'""",
            ("local SQL Server integration tests",),
        )
        if cursor.rowcount != 1:
            claim.rollback()
            pytest.fail(
                "La base ya fue reclamada por otra ejecución; selecciona una "
                "base nueva preparada con otro nombre."
            )
        claim.commit()
    finally:
        claim.close()

    suffix = uuid.uuid4().hex[:8]

    from fastapi.testclient import TestClient

    with TestClient(module.app) as client:
        super_headers = _login(client, TEST_ADMIN_EMAIL)
        office_a_response = client.post(
            f"{API}/oficinas",
            headers=super_headers,
            json=_office_payload(f"SQL Test A {suffix}", "TSA"),
        )
        assert office_a_response.status_code == 201, office_a_response.text
        office_a = office_a_response.json()["id"]

        office_b_response = client.post(
            f"{API}/oficinas",
            headers=super_headers,
            json=_office_payload(f"SQL Test B {suffix}", "TSB"),
        )
        assert office_b_response.status_code == 201, office_b_response.text
        office_b = office_b_response.json()["id"]

        emails = {
            "admin_a": f"sql-admin-{suffix}@example.com",
            "cashier_a": f"sql-cashier-{suffix}@example.com",
            "consultas_a": f"sql-consultas-{suffix}@example.com",
            "cashier_b": f"sql-cashier-b-{suffix}@example.com",
        }
        _create_user(client, super_headers, "101", emails["admin_a"], "Administrador", office_a)
        _create_user(client, super_headers, "102", emails["cashier_a"], "Caja", office_a)
        _create_user(client, super_headers, "103", emails["consultas_a"], "Consultas", office_a)
        _create_user(client, super_headers, "201", emails["cashier_b"], "Caja", office_b)
        headers = {
            role: _login(client, email)
            for role, email in emails.items()
        }

        student_response = client.post(
            f"{API}/estudiantes",
            headers=super_headers,
            json={
                "ci": f"TEST-{suffix}-STU",
                "cu": f"SQL{suffix[:5]}",
                "nombre": "Estudiante de prueba A",
                "gestion": date.today().year,
                "office_id": office_a,
            },
        )
        assert student_response.status_code == 201, student_response.text
        student_a = student_response.json()["id"]

        foreign_student_response = client.post(
            f"{API}/estudiantes",
            headers=super_headers,
            json={
                "ci": f"TEST-{suffix}-B",
                "cu": f"OTR{suffix[:5]}",
                "nombre": "Estudiante de prueba B",
                "gestion": date.today().year,
                "office_id": office_b,
            },
        )
        assert foreign_student_response.status_code == 201, foreign_student_response.text
        student_b = foreign_student_response.json()["id"]

        concept_response = client.post(
            f"{API}/tipos-pagos",
            headers=headers["admin_a"],
            json={
                "nombre": f"Concepto local {suffix}",
                "monto": "25.00",
                "descripcion": "Solo para pruebas de integración SQL",
                "inicio": "2020-01-01",
                "fin": None,
            },
        )
        assert concept_response.status_code == 201, concept_response.text
        concept_id = concept_response.json()["id"]

        monday = {
            "dia": "lunes",
            "desde": "08:00",
            "hasta": "18:00",
        }
        room_response = client.post(
            f"{API}/ambientes",
            headers=headers["admin_a"],
            json={
                "nombre": f"Ambiente local {suffix}",
                "descripcion": "Recurso de pruebas de integración",
                "horarios": [monday],
            },
        )
        assert room_response.status_code == 201, room_response.text
        room_id = room_response.json()["id"]

        tariff_response = client.post(
            f"{API}/tarifas-ambientes",
            headers=headers["admin_a"],
            json={
                "ambiente_id": room_id,
                "nombre": f"Tarifa local {suffix}",
                "modalidad": "hora",
                "monto": "25.00",
                "descripcion": "",
            },
        )
        assert tariff_response.status_code == 201, tariff_response.text
        tariff_id = tariff_response.json()["id"]

        person_response = client.post(
            f"{API}/personas",
            headers=headers["admin_a"],
            json={"ci": f"TEST-{suffix}-PER", "nombre": "Persona de prueba SQL"},
        )
        assert person_response.status_code == 201, person_response.text
        person_id = person_response.json()["id"]

        yield {
            "module": module,
            "client": client,
            "database": database,
            "read": lambda statement, params=(): _read_rows(
                module, statement, params
            ),
            "suffix": suffix,
            "super": super_headers,
            "headers": headers,
            "emails": emails,
            "office_a": office_a,
            "office_b": office_b,
            "student_a": student_a,
            "student_b": student_b,
            "concept_id": concept_id,
            "room_id": room_id,
            "tariff_id": tariff_id,
            "person_id": person_id,
        }


def _student_payload(suffix, name, office_id=None):
    payload = {
        "ci": f"CRUD-{suffix}-{uuid.uuid4().hex[:6]}",
        "cu": f"CU{uuid.uuid4().hex[:6]}",
        "nombre": name,
        "gestion": date.today().year,
    }
    if office_id is not None:
        payload["office_id"] = office_id
    return payload


def test_real_ddl_identity_user_code_and_non_persisted_display(local_sql):
    state = local_sql
    rows = state["read"](
        """SELECT OBJECT_NAME(c.object_id),c.is_identity
           FROM sys.columns c
           WHERE c.name=N'id' AND OBJECT_NAME(c.object_id) IN
             (N'oficinas',N'personas',N'estudiantes',N'tipos_pagos',N'ambientes',
              N'ambiente_horarios',N'tarifas_ambientes',N'pagos',N'pago_items',
              N'alquileres',N'alquiler_intervalos',N'ocupacion_intervalos')"""
    )
    identities = {name for name, is_identity in rows if is_identity}
    assert identities == {
        "oficinas",
        "personas",
        "estudiantes",
        "tipos_pagos",
        "ambientes",
        "ambiente_horarios",
        "tarifas_ambientes",
        "pagos",
        "pago_items",
        "alquileres",
        "alquiler_intervalos",
        "ocupacion_intervalos",
    }

    user_type = state["read"](
        """SELECT t.name,c.max_length
           FROM sys.columns c JOIN sys.types t ON t.user_type_id=c.user_type_id
           WHERE c.object_id=OBJECT_ID(N'dbo.usuarios') AND c.name=N'id'"""
    )
    assert user_type == [("char", 3)]
    persisted_display = state["read"](
        "SELECT OBJECT_NAME(object_id) FROM sys.columns WHERE name=N'comprobante_display'"
    )
    assert persisted_display == []

    index_rows = state["read"](
        """SELECT OBJECT_NAME(object_id),is_unique,filter_definition
           FROM sys.indexes
           WHERE name IN (N'IX_pagos_recibo',N'IX_alq_recibo')"""
    )
    assert {row[0] for row in index_rows} == {"pagos", "alquileres"}
    assert all(is_unique and filter_definition for _, is_unique, filter_definition in index_rows)

    connection = state["module"].pyodbc.connect(
        state["module"]._connection_string(), autocommit=False
    )
    try:
        cursor = connection.cursor()
        with pytest.raises(state["module"].pyodbc.IntegrityError):
            cursor.execute(
                """INSERT INTO dbo.usuarios(id,email,nombre,rol,id_oficina,password_hash)
                   VALUES(?,?,?,?,?,?)""",
                (
                    "A01",
                    f"invalid-user-{state['suffix']}@example.invalid",
                    "Código inválido",
                    "Caja",
                    int(state["office_a"]),
                    "not-a-real-password",
                ),
            )
            connection.commit()
        connection.rollback()
    finally:
        connection.close()

    assert state["office_a"].isdigit()
    assert state["student_a"].isdigit()
    assert state["concept_id"].isdigit()
    assert state["room_id"].isdigit()
    assert state["tariff_id"].isdigit()
    assert state["person_id"].isdigit()
    assert state["headers"]["admin_a"]


def test_role_office_scoping_and_real_crud(local_sql):
    client = local_sql["client"]
    admin = local_sql["headers"]["admin_a"]
    cashier = local_sql["headers"]["cashier_a"]
    consultas = local_sql["headers"]["consultas_a"]
    superadmin = local_sql["super"]
    office_a = local_sql["office_a"]
    office_b = local_sql["office_b"]

    visible_offices = client.get(f"{API}/oficinas", headers=admin).json()["items"]
    assert [row["id"] for row in visible_offices] == [office_a]
    assert client.get(
        f"{API}/usuarios?office_id={office_b}", headers=admin
    ).status_code == 403
    assert client.get(f"{API}/usuarios", headers=cashier).status_code == 403
    assert client.post(
        f"{API}/estudiantes",
        headers=consultas,
        json=_student_payload(local_sql["suffix"], "Sin permiso"),
    ).status_code == 403
    assert client.get(
        f"{API}/estudiantes?office_id={office_b}", headers=cashier
    ).status_code == 403
    assert client.put(
        f"{API}/estudiantes/{local_sql['student_b']}",
        headers=admin,
        json=_student_payload(local_sql["suffix"], "Fuera de oficina"),
    ).status_code == 403

    foreign_office_create = client.post(
        f"{API}/estudiantes",
        headers=cashier,
        json=_student_payload(local_sql["suffix"], "No debe cruzar oficina", office_b),
    )
    assert foreign_office_create.status_code == 403

    student = client.post(
        f"{API}/estudiantes",
        headers=admin,
        json=_student_payload(local_sql["suffix"], "CRUD antes"),
    )
    assert student.status_code == 201, student.text
    student_id = student.json()["id"]
    assert student_id.isdigit()
    edited_student = client.put(
        f"{API}/estudiantes/{student_id}",
        headers=admin,
        json={**_student_payload(local_sql["suffix"], "CRUD después"), "office_id": office_a},
    )
    assert edited_student.status_code == 200, edited_student.text
    assert edited_student.json()["nombre"] == "CRUD después"
    assert client.put(
        f"{API}/estudiantes/{student_id}",
        headers=cashier,
        json=_student_payload(local_sql["suffix"], "Caja no puede editar"),
    ).status_code == 403
    assert client.delete(f"{API}/estudiantes/{student_id}", headers=admin).status_code == 200
    cashier_student = client.post(
        f"{API}/estudiantes",
        headers=cashier,
        json=_student_payload(local_sql["suffix"], "Alta permitida a Caja"),
    )
    assert cashier_student.status_code == 201, cashier_student.text
    assert cashier_student.json()["id"].isdigit()
    assert client.delete(
        f"{API}/estudiantes/{cashier_student.json()['id']}", headers=cashier
    ).status_code == 403

    user_create = client.post(
        f"{API}/usuarios",
        headers=admin,
        json={
            "codigo": "A04",
            "email": f"sql-transient-{local_sql['suffix']}@example.com",
            "nombre": "Usuario transitorio",
            "password": TEST_PASSWORD,
            "rol": "Caja",
            "office_id": office_a,
        },
    )
    assert user_create.status_code == 201, user_create.text
    assert user_create.json()["id"] == "104"
    user_update = client.put(
        f"{API}/usuarios/104",
        headers=admin,
        json={"nombre": "Usuario actualizado"},
    )
    assert user_update.status_code == 200, user_update.text
    assert user_update.json()["nombre"] == "Usuario actualizado"
    assert client.put(
        f"{API}/usuarios/104", headers=admin, json={"codigo": "105"}
    ).status_code == 400
    assert client.delete(f"{API}/usuarios/104", headers=admin).status_code == 200

    assert client.post(
        f"{API}/oficinas",
        headers=admin,
        json=_office_payload(f"CRUD Office forbidden {local_sql['suffix']}", "TSC"),
    ).status_code == 403
    temporary_office = client.post(
        f"{API}/oficinas",
        headers=superadmin,
        json=_office_payload(f"CRUD Office {local_sql['suffix']}", "TSC"),
    )
    assert temporary_office.status_code == 201, temporary_office.text
    temporary_id = temporary_office.json()["id"]
    assert temporary_id.isdigit()
    updated_office = client.put(
        f"{API}/oficinas/{temporary_id}",
        headers=superadmin,
        json=_office_payload(f"CRUD Office updated {local_sql['suffix']}", "TSC"),
    )
    assert updated_office.status_code == 200, updated_office.text
    assert updated_office.json()["nombre"].endswith("updated " + local_sql["suffix"])
    assert client.delete(
        f"{API}/oficinas/{temporary_id}", headers=superadmin
    ).status_code == 200


def _rental_payload(state, day, start, end):
    return {
        "ambiente_id": state["room_id"],
        "tarifa_id": state["tariff_id"],
        "fecha": day,
        "desde": start,
        "hasta": end,
        "cliente_tipo": "persona",
        "cliente_id": state["person_id"],
    }


def test_shared_receipts_idempotent_rental_payment_and_annulments(local_sql):
    client = local_sql["client"]
    admin = local_sql["headers"]["admin_a"]
    cashier = local_sql["headers"]["cashier_a"]
    date_paid = date.today().isoformat()
    payment_payload = {
        "id_estudiante": local_sql["student_a"],
        "fecha_pago": date_paid,
        "id_tipo_pago": local_sql["concept_id"],
        "cantidad": 1,
    }
    payment_one = client.post(
        f"{API}/pagos", headers=cashier, json=payment_payload
    )
    assert payment_one.status_code == 201, payment_one.text
    payment_one_row = payment_one.json()
    assert payment_one_row["id"].isdigit()
    assert payment_one_row["cod_comprobante"] == "00001"
    assert payment_one_row["comprobante_display"] == (
        f"TSA-00001 / {payment_one_row['gestion']}"
    )

    reservation = client.post(
        f"{API}/alquileres",
        headers=cashier,
        json=_rental_payload(local_sql, _monday_after(), "09:00", "10:00"),
    )
    assert reservation.status_code == 201, reservation.text
    rental_id = reservation.json()["id"]
    assert rental_id.isdigit()
    assert reservation.json()["estado"] == "reservado"
    assert reservation.json()["comprobante_display"] is None

    paid = client.post(f"{API}/alquileres/{rental_id}/pagar", headers=cashier)
    repeated_payment = client.post(
        f"{API}/alquileres/{rental_id}/pagar", headers=cashier
    )
    assert paid.status_code == 200, paid.text
    assert repeated_payment.status_code == 200, repeated_payment.text
    paid_row = paid.json()
    assert paid_row["estado"] == "pagado"
    assert paid_row["cod_comprobante"] == "00002"
    assert repeated_payment.json()["cod_comprobante"] == paid_row["cod_comprobante"]
    assert paid_row["comprobante_display"] == (
        f"TSA-00002 / {paid_row['gestion']}"
    )
    allocation = local_sql["read"](
        """SELECT COUNT(*) FROM dbo.comprobante_asignaciones
           WHERE origen=N'alquiler' AND origen_id=?""",
        (int(rental_id),),
    )
    assert allocation[0][0] == 1

    payment_two = client.post(
        f"{API}/pagos", headers=cashier, json=payment_payload
    )
    assert payment_two.status_code == 201, payment_two.text
    assert payment_two.json()["cod_comprobante"] == "00003"

    void_payment = client.post(
        f"{API}/pagos/{payment_one_row['id']}/anular", headers=admin
    )
    assert void_payment.status_code == 200, void_payment.text
    stored_payment = client.get(
        f"{API}/pagos/{payment_one_row['id']}", headers=admin
    )
    assert stored_payment.status_code == 200
    assert stored_payment.json()["anulado"] is True
    assert client.post(
        f"{API}/pagos/{payment_one_row['id']}/anular", headers=admin
    ).status_code == 400

    void_rental = client.post(
        f"{API}/alquileres/{rental_id}/anular", headers=admin
    )
    assert void_rental.status_code == 200, void_rental.text
    assert void_rental.json()["estado"] == "cancelado"
    assert void_rental.json()["cod_comprobante"] == "00002"
    assert client.post(
        f"{API}/alquileres/{rental_id}/anular", headers=admin
    ).status_code == 200

    stored_payment_columns = local_sql["read"](
        """SELECT name FROM sys.columns
           WHERE object_id IN (OBJECT_ID(N'dbo.pagos'),OBJECT_ID(N'dbo.alquileres'))
             AND name=N'comprobante_display'"""
    )
    assert stored_payment_columns == []
    stored_codes = local_sql["read"](
        """SELECT cod_comprobante FROM dbo.pagos WHERE id=?
           UNION ALL
           SELECT cod_comprobante FROM dbo.alquileres WHERE id=?""",
        (int(payment_one_row["id"]), int(rental_id)),
    )
    assert {row[0] for row in stored_codes} == {"00001", "00002"}


def test_concurrent_overlapping_reservations_only_one_succeeds(local_sql):
    import httpx

    state = local_sql
    day = _monday_after(weeks=2)
    headers = state["headers"]["cashier_a"]
    payload = _rental_payload(state, day, "14:00", "15:00")

    async def attempt():
        transport = httpx.ASGITransport(app=state["module"].app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://sql-local-integration"
        ) as client:
            return await client.post(
                f"{API}/alquileres", headers=headers, json=payload
            )

    async def race():
        return await asyncio.gather(attempt(), attempt())

    responses = asyncio.run(race())
    assert sorted(response.status_code for response in responses) == [201, 409], [
        (response.status_code, response.text) for response in responses
    ]
    reservations = state["client"].get(
        f"{API}/alquileres",
        headers=headers,
        params={
            "ambiente_id": state["room_id"],
            "fecha_desde": day,
            "fecha_hasta": day,
        },
    )
    assert reservations.status_code == 200, reservations.text
    assert len(reservations.json()) == 1
