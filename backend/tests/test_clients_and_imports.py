"""Unified clients and selectable directory imports on disposable Mongo databases."""
import asyncio
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from test_rentals_integration import (
    API, _actor, _client, _rental_payload, _tariff_payload, mongo_rental_api,
)
from client_models import ClienteCreate
import import_services


@pytest.mark.parametrize("role", ["SuperAdmin", "Administrador", "Caja"])
def test_client_crud_shared_catalog_and_generated_id(mongo_rental_api, role):
    state = mongo_rental_api

    async def scenario():
        async with await _client(_actor(role)) as client:
            body = {"id": "external-id", "ci": " 987-X ", "cu": " CU-X ", "nombre": " Nombre Completo "}
            created = await client.post(f"{API}/clientes", json=body)
            assert created.status_code == 201, created.text
            row = created.json()
            assert row == {"id": row["id"], "ci": "987-X", "cu": "CU-X", "nombre": "Nombre Completo"}
            assert str(UUID(row["id"])) == row["id"] and row["id"] != "external-id"
            assert (await client.post(f"{API}/clientes", json={**body, "ci": "987-x", "cu": ""})).status_code == 400
            assert (await client.post(f"{API}/clientes", json={**body, "ci": "", "cu": "cu-x"})).status_code == 400
            assert (await client.post(f"{API}/clientes", json={"ci": "", "cu": "", "nombre": "Nada"})).status_code == 422
            updated = await client.put(f'{API}/clientes/{row["id"]}', json={"ci": "987-X", "cu": "", "nombre": "Actualizado"})
            assert updated.status_code == 200 and updated.json()["id"] == row["id"]
            assert (await client.put(f"{API}/clientes/no-existe", json=body)).status_code == 404
        async with await _client(_actor("Caja", "office-b")) as other_office:
            listed = await other_office.get(f"{API}/clientes", params={"textoBuscar": "987-X"})
            assert [r["id"] for r in listed.json()["items"]] == [row["id"]]
            search = await other_office.get(f"{API}/clientes/buscar", params={"q": "Actualizado"})
            assert search.json()[0]["id"] == row["id"]
            assert (await other_office.delete(f'{API}/clientes/{row["id"]}')).status_code == 200
            assert (await other_office.delete(f'{API}/clientes/{row["id"]}')).status_code == 404
        assert await state["db"].clientes.count_documents({"ci_key": "987-x"}) == 0

    state["loop"].run_until_complete(scenario())


def test_consultas_cannot_write_clients_or_import(mongo_rental_api):
    async def scenario():
        async with await _client(_actor("Consultas")) as client:
            body = {"ci": "100", "nombre": "Consulta"}
            assert (await client.get(f"{API}/clientes")).status_code == 403
            assert (await client.get(f"{API}/clientes/buscar", params={"q": "Nombre"})).status_code == 403
            assert (await client.post(f"{API}/clientes", json=body)).status_code == 403
            assert (await client.put(f"{API}/clientes/person-a", json=body)).status_code == 403
            assert (await client.delete(f"{API}/clientes/person-a")).status_code == 403
            assert (await client.get(f"{API}/clientes/importacion")).status_code == 403
    mongo_rental_api["loop"].run_until_complete(scenario())


@pytest.mark.parametrize("role", ["Administrador", "Caja", "Consultas"])
def test_only_superadmin_has_user_crud_and_import(mongo_rental_api, role):
    async def scenario():
        async with await _client(_actor(role)) as client:
            body = {"codigo": "123", "nombre": "Usuario", "email": "usuario@example.com",
                    "password": "test-password", "rol": "Caja", "office_id": "office-a"}
            assert (await client.get(f"{API}/usuarios")).status_code == 403
            assert (await client.get(f"{API}/usuarios/list")).status_code == 403
            assert (await client.get(f"{API}/usuarios/importacion")).status_code == 403
            assert (await client.post(f"{API}/usuarios", json=body)).status_code == 403
            assert (await client.put(f"{API}/usuarios/no-existe", json={"nombre": "Editado"})).status_code == 403
            assert (await client.delete(f"{API}/usuarios/no-existe")).status_code == 403
            assert (await client.get(f"{API}/reportes/registradores")).status_code == 200
    mongo_rental_api["loop"].run_until_complete(scenario())


def test_clients_work_in_payments_edit_search_receipts_and_rentals(mongo_rental_api):
    state = mongo_rental_api
    async def scenario():
        async with await _client(_actor()) as admin:
            await state["db"].clasificadores_presupuestarios.insert_one({
                "id": "test-budget-classifier",
                "codigo": "12100",
                "nombre": "Venta de bienes",
                "activa": True,
            })
            concept = await admin.post(f"{API}/tipos-pagos", json={
                "codigo": "10001",
                "nombre": "Concepto Clientes",
                "monto": 10,
                "inicio": state["monday"],
                "id_clasificador": "test-budget-classifier",
            })
            assert concept.status_code == 201, concept.text
        async with await _client(_actor("Caja")) as client:
            one = (await client.post(f"{API}/clientes", json={"ci": "100-X", "cu": "CU100", "nombre": "Primer Cliente"})).json()
            two = (await client.post(f"{API}/clientes", json={"ci": "200-X", "nombre": "Segundo Cliente"})).json()
            payment = await client.post(f"{API}/pagos", json={"cliente_id": one["id"], "fecha_pago": state["monday"]})
            assert payment.status_code == 201, payment.text
            p = payment.json()
            assert p["cliente_nombre"] == one["nombre"] and p["cliente_ci"] == one["ci"]
            assert "id_estudiante" not in p and "estudiante_nombre" not in p
            assert (await client.delete(f'{API}/clientes/{one["id"]}')).status_code == 400
            added = await client.post(f'{API}/pagos/{p["id"]}/items', json={
                "id_tipo_pago": concept.json()["id"], "cantidad": 1,
            })
            assert added.status_code == 200, added.text
            finalized = await client.post(f'{API}/pagos/{p["id"]}/finalizar')
            assert finalized.status_code == 200, finalized.text
        async with await _client(_actor()) as admin:
            edited = await admin.put(f'{API}/pagos/{p["id"]}', json={"cliente_id": two["id"], "fecha_pago": state["monday"]})
            assert edited.status_code == 200 and edited.json()["cliente_nombre"] == two["nombre"], edited.text
            found = await admin.get(f"{API}/pagos", params={"q": "Segundo Cliente"})
            assert found.json()["items"][0]["cliente_id"] == two["id"]
            tariff = await admin.post(f"{API}/tarifas-ambientes", json=_tariff_payload("room-a"))
            rental = await admin.post(f"{API}/alquileres", json=_rental_payload("room-a", tariff.json()["id"], state["monday"], cliente_id=one["id"]))
            assert rental.status_code == 201, rental.text
            assert rental.json()["cliente_nombre"] == one["nombre"]
            assert "cliente_tipo" not in rental.json()
            assert (await admin.delete(f'{API}/clientes/{one["id"]}')).status_code == 400
            assert (await admin.get(f"{API}/estudiantes")).status_code == 404
            assert (await admin.get(f"{API}/personas")).status_code == 404
    state["loop"].run_until_complete(scenario())


def test_directory_normalizes_names_discards_ids_and_requires_valid_fields():
    assert import_services.normalize_record(
        {"Id": "untrusted", "CI": " 100 ", "CU": " A ", "Nombre Completo": " Nombre "}, "clientes"
    ) == {"ci": "100", "cu": "A", "nombre": "Nombre"}
    assert import_services.normalize_record(
        {"Id": "untrusted", "Código": "A07", "Nombre Completo": "Usuario", "Email": "usuario@example.com"}, "usuarios"
    ) == {"codigo": "A07", "nombre": "Usuario", "email": "usuario@example.com"}
    with pytest.raises(ValidationError):
        ClienteCreate(ci=" ", cu="", nombre="Nombre")
    with pytest.raises(ValidationError):
        ClienteCreate(ci="1", nombre=" ")


def test_directory_errors_filtering_and_selectable_creation(mongo_rental_api, monkeypatch):
    state = mongo_rental_api
    real_client = httpx.AsyncClient
    rows = [
        {"Id": "external-1", "CI": "881", "CU": "", "Nombre Completo": "Importado"},
        {"CI": "882", "Nombre Completo": "Otro"},
    ]
    def fake_client(**kwargs):
        return real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=rows)), **kwargs)
    async def scenario():
        monkeypatch.delenv("CLIENTS_IMPORT_API_URL", raising=False)
        async with await _client(_actor("Caja")) as client:
            unconfigured = await client.get(f"{API}/clientes/importacion")
            assert unconfigured.status_code == 503
            monkeypatch.setenv("CLIENTS_IMPORT_API_URL", "https://directory.example/clients")
            monkeypatch.setattr(import_services.httpx, "AsyncClient", fake_client)
            result = await client.get(f"{API}/clientes/importacion", params={"q": "Importado"})
            assert result.status_code == 200 and len(result.json()) == 1
            assert await state["db"].clientes.count_documents({"ci": "881"}) == 0
            created = await client.post(f"{API}/clientes", json=result.json()[0])
            assert created.status_code == 201 and created.json()["id"] != "external-1"
            rows[:] = [{"CI": "", "CU": "", "Nombre Completo": "Inválido"}]
            assert (await client.get(f"{API}/clientes/importacion")).status_code == 502
        monkeypatch.setenv("USERS_IMPORT_API_URL", "https://directory.example/users")
        rows[:] = [{"Código": "014", "Nombre Completo": "Importado Usuario", "Email": "importado@example.com"}]
        # _client constructs an ASGI client, not the patched integration client.
        monkeypatch.setattr(import_services.httpx, "AsyncClient", real_client)
        async with await _client(_actor("SuperAdmin")) as admin:
            monkeypatch.setattr(import_services.httpx, "AsyncClient", fake_client)
            directory = await admin.get(f"{API}/usuarios/importacion")
            assert directory.status_code == 200
            payload = {**directory.json()[0], "rol": "Caja", "office_id": "office-a", "password": "test-password"}
            imported = await admin.post(f"{API}/usuarios", json=payload)
            assert imported.status_code == 201
            user = imported.json()
            assert user["id"] != user["codigo"] and user["codigo"] == "014"
            changed = await admin.put(f'{API}/usuarios/{user["id"]}', json={"email": "editado@example.com"})
            assert changed.status_code == 200 and changed.json()["email"] == "editado@example.com"
    state["loop"].run_until_complete(scenario())


@pytest.mark.parametrize("response", [
    httpx.Response(500), httpx.Response(302, headers={"Location": "https://another.example"}),
    httpx.Response(200, json={"items": []}), httpx.Response(200, content=b"not json"),
])
def test_directory_bad_responses_fail_explicitly(monkeypatch, response):
    real_client = httpx.AsyncClient
    monkeypatch.setenv("CLIENTS_IMPORT_API_URL", "https://directory.example")
    monkeypatch.setattr(import_services.httpx, "AsyncClient", lambda **kw: real_client(
        transport=httpx.MockTransport(lambda request: response), **kw,
    ))
    with pytest.raises(HTTPException) as error:
        asyncio.run(import_services.directory_results("clientes"))
    assert error.value.status_code == 502
