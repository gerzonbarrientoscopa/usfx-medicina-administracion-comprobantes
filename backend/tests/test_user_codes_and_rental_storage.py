"""CRUD codes and derived rental receipts against disposable Mongo databases."""
from uuid import UUID

from test_rentals_integration import (
    API, _actor, _client, _tariff_payload, _rental_payload, mongo_rental_api,
    empty_startup_database,
)
import server


def test_manual_codes_keep_mongo_uuid_and_support_legacy_users(mongo_rental_api):
    state = mongo_rental_api

    async def scenario():
        await state["db"].usuarios.create_index(
            "codigo", unique=True, partialFilterExpression={"codigo": {"$type": "string"}}
        )
        body = {"codigo": "A07", "nombre": "Caja", "email": "code@example.com",
                "password": "test-pass", "rol": "Caja", "office_id": "office-a"}
        async with await _client(_actor("SuperAdmin")) as client:
            created = await client.post(f"{API}/usuarios", json=body)
            assert created.status_code == 201, created.text
            user = created.json()
            assert str(UUID(user["id"])) == user["id"]
            assert user["codigo"] == "A07"
            duplicate = await client.post(f"{API}/usuarios", json={
                **body, "email": "duplicate@example.com", "office_id": "office-b",
            })
            assert duplicate.status_code == 400
            for code in ("7", "0007", "A-1", "ABCD", "١٢٣"):
                response = await client.post(f"{API}/usuarios", json={**body, "codigo": code})
                assert response.status_code == 422
            reserved = await client.post(f"{API}/usuarios", json={**body, "codigo": "000"})
            assert reserved.status_code == 400
            changed = await client.put(f'{API}/usuarios/{user["id"]}', json={"codigo": "008"})
            assert changed.status_code == 400
            updated = await client.put(f'{API}/usuarios/{user["id"]}', json={"nombre": "Actualizado"})
            assert updated.status_code == 200 and updated.json()["codigo"] == "A07"
            await state["db"].usuarios.insert_one({
                "id": "legacy-user", "nombre": "Anterior", "email": "legacy@example.com",
                "rol": "Caja", "office_id": "office-a", "password_hash": "unused",
            })
            assigned = await client.put(f"{API}/usuarios/legacy-user", json={"codigo": "B08"})
            assert assigned.status_code == 200 and assigned.json()["codigo"] == "B08"
            deleted = await client.delete(f'{API}/usuarios/{user["id"]}')
            assert deleted.status_code == 200
        async with await _client(_actor("Caja")) as caja:
            assert (await caja.post(f"{API}/usuarios", json=body)).status_code == 403

    state["loop"].run_until_complete(scenario())


def test_rental_receipt_is_calculated_not_stored(mongo_rental_api):
    state = mongo_rental_api

    async def scenario():
        async with await _client(_actor()) as client:
            tariff = await client.post(f"{API}/tarifas-ambientes", json=_tariff_payload("room-a"))
            assert tariff.status_code == 201
            created = await client.post(f"{API}/alquileres", json=_rental_payload(
                "room-a", tariff.json()["id"], state["monday"],
            ))
            assert created.status_code == 201, created.text
            rid = created.json()["id"]
            assert created.json()["comprobante_display"] is None
            assert "comprobante_display" not in await state["db"].alquileres.find_one({"id": rid})
            paid = await client.post(f"{API}/alquileres/{rid}/pagar")
            assert paid.status_code == 200, paid.text
            receipt = paid.json()
            expected = f'RTA-{receipt["cod_comprobante"]} / {receipt["gestion"]}'
            assert receipt["comprobante_display"] == expected
            assert "comprobante_display" not in await state["db"].alquileres.find_one({"id": rid})
            repeated = await client.post(f"{API}/alquileres/{rid}/pagar")
            assert repeated.json()["comprobante_display"] == expected
            assert (await client.get(f"{API}/alquileres/{rid}")).json()["comprobante_display"] == expected
            listed = await client.get(f"{API}/alquileres", params={
                "ambiente_id": "room-a", "fecha_desde": state["monday"], "fecha_hasta": state["monday"],
            })
            assert listed.json()[0]["comprobante_display"] == expected
            annulled = await client.post(f"{API}/alquileres/{rid}/anular")
            assert annulled.status_code == 200 and annulled.json()["comprobante_display"] == expected

    state["loop"].run_until_complete(scenario())


def test_startup_removes_only_derived_receipt_storage(empty_startup_database):
    state = empty_startup_database

    async def scenario():
        await state["db"].oficinas.insert_one({
            "id": "office-legacy", "nombre": "Legacy", "nombre_key": "legacy",
            "prefijo_comprobante": "ABC", "suboficina": "", "activa": True,
        })
        await state["db"].alquileres.insert_one({
            "id": "legacy-rental", "office_id": "office-legacy",
            "estado": "cancelado", "comprobante_display": "old",
            "cod_comprobante": "00003", "prefijo_comprobante": "ABC", "gestion": 2026,
        })
        await server.startup()
        rental = await state["db"].alquileres.find_one({"id": "legacy-rental"})
        assert "comprobante_display" not in rental
        assert rental["cod_comprobante"] == "00003"
        admin = await state["db"].usuarios.find_one({"rol": "SuperAdmin"})
        assert admin["codigo"] == "000"
        assert str(UUID(admin["id"])) == admin["id"]

    state["loop"].run_until_complete(scenario())
