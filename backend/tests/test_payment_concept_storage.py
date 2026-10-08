"""Concepts belong to payment items; legacy receipts remain readable/editable."""
import pytest

from test_rentals_integration import API, _actor, _client, mongo_rental_api


@pytest.mark.parametrize("draft", [False, True])
def test_itemized_concept_is_not_duplicated_on_payment(mongo_rental_api, draft):
    state = mongo_rental_api

    async def scenario():
        await state["db"].clasificadores_presupuestarios.insert_one({
            "id": "classifier", "codigo": "12100", "nombre": "Clasificador",
            "activa": True,
        })
        for ident, name, amount in (("first", "Primer concepto", 10), ("second", "Segundo concepto", 15)):
            await state["db"].tipos_pagos.insert_one({
                "id": ident, "office_id": state["office_a"], "codigo": ident,
                "nombre": name, "monto": amount, "id_clasificador": "classifier",
            })
        async with await _client(_actor()) as client:
            payload = {"cliente_id": "person-a", "fecha_pago": state["monday"]}
            if not draft:
                payload.update(id_tipo_pago="first", cantidad=2)
            created = await client.post(f"{API}/pagos", json=payload)
            assert created.status_code == 201, created.text
            pid = created.json()["id"]
            if draft:
                added = await client.post(f"{API}/pagos/{pid}/items", json={
                    "id_tipo_pago": "first", "cantidad": 2,
                })
                assert added.status_code == 200, added.text
                finalized = await client.post(f"{API}/pagos/{pid}/finalizar")
                assert finalized.status_code == 200, finalized.text
            stored = await state["db"].pagos.find_one({"id": pid})
            assert "id_tipo_pago" not in stored
            assert stored["items"][0]["id_tipo_pago"] == "first"
            fetched = await client.get(f"{API}/pagos/{pid}")
            assert fetched.status_code == 200, fetched.text
            assert fetched.json()["id_tipo_pago"] == "first"
            edited = await client.put(f"{API}/pagos/{pid}", json={
                **payload, "id_tipo_pago": "second", "cantidad": 3,
            })
            assert edited.status_code == 200, edited.text
            assert edited.json()["id_tipo_pago"] == "second"
            assert edited.json()["total"] == 45
            stored = await state["db"].pagos.find_one({"id": pid})
            assert "id_tipo_pago" not in stored
            assert stored["items"][0]["id_tipo_pago"] == "second"
            assert stored["items"][0]["total"] == 45
            found = await client.get(f"{API}/pagos", params={"id_tipo_pago": "second"})
            assert [row["id"] for row in found.json()["items"]] == [pid]

            # Simulate a receipt predating payment items.
            await state["db"].pagos.update_one({"id": pid}, {
                "$unset": {"items": ""},
                "$set": {"id_tipo_pago": "first", "monto": 10, "cantidad": 2, "total": 20},
            })
            legacy = await client.get(f"{API}/pagos/{pid}")
            assert legacy.status_code == 200, legacy.text
            assert legacy.json()["id_tipo_pago"] == "first"
            found = await client.get(f"{API}/pagos", params={"id_tipo_pago": "first"})
            assert [row["id"] for row in found.json()["items"]] == [pid]
            edited_legacy = await client.put(f"{API}/pagos/{pid}", json={
                **payload, "id_tipo_pago": "second", "cantidad": 3,
            })
            assert edited_legacy.status_code == 200, edited_legacy.text
            assert edited_legacy.json()["id_tipo_pago"] == "second"
            assert edited_legacy.json()["total"] == 45

    state["loop"].run_until_complete(scenario())
