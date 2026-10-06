"""Combined income and receipt search, using the disposable Mongo fixture."""
from datetime import datetime, timezone

import pytest

from test_rentals_integration import API, _actor, _client, mongo_rental_api


def test_income_and_receipt_search(mongo_rental_api):
    state = mongo_rental_api

    async def scenario():
        db = state["db"]
        year = datetime.now(timezone.utc).year
        day = f"{year}-03-12"
        next_day = f"{year}-03-13"
        await db.pagos.insert_one({
            "id": "student-payment", "office_id": "office-a", "cliente_id": "student-a",
            "cod_comprobante": "00001", "prefijo_comprobante": "RTA", "gestion": year,
            "fecha_pago": day, "total": 25.0, "estado": "finalizado",
            "anulado": False, "created_by": "user-Administrador-office-a",
            "created_at": f"{day}T12:00:00Z",
        })
        await db.pagos.insert_one({
            "id": "void-payment", "office_id": "office-a", "cliente_id": "student-a",
            "cod_comprobante": "00002", "prefijo_comprobante": "RTA", "gestion": year,
            "fecha_pago": day, "total": 8.0, "estado": "finalizado",
            "anulado": True, "created_by": "user-Administrador-office-a",
            "created_at": f"{day}T12:01:00Z",
        })
        rental = {
            "office_id": "office-a", "cliente_nombre": "Cliente Alquiler",
            "cliente_ci": "777", "ambiente_nombre": "Sala Mayor", "tarifa_nombre": "Hora",
            "fecha": next_day, "total": 60.0, "cantidad": 1, "monto": 60.0,
            "paid_by": "user-Administrador-office-a", "gestion": year,
            "cod_comprobante": "00003", "prefijo_comprobante": "RTA",
            "comprobante_display": f"RTA-00003 / {year}",
            "fecha_pago": f"{day}T23:59:00+00:00",
        }
        await db.alquileres.insert_many([
            {"id": "paid-rental", "estado": "pagado", **rental},
            {
                "id": "void-rental",
                "estado": "cancelado",
                **{**rental, "total": 40.0, "cod_comprobante": "00006"},
            },
            {"id": "reserved-rental", "estado": "reservado", **{**rental, "cod_comprobante": None}},
            {"id": "cancelled-rental", "estado": "cancelado", **{**rental, "cod_comprobante": None}},
            {"id": "other-office-rental", "estado": "pagado",
             **{**rental, "office_id": "office-b", "prefijo_comprobante": "RTB", "cod_comprobante": "00004"}},
            {"id": "other-date-rental", "estado": "pagado",
             **{**rental, "fecha_pago": f"{next_day}T00:00:00+00:00", "cod_comprobante": "00005"}},
        ])
        async with await _client(_actor()) as client:
            params = {"periodo": "rango", "desde": day, "hasta": day}
            response = await client.get(f"{API}/reportes", params=params)
            assert response.status_code == 200, response.text
            report = response.json()
            assert {a["id"] for a in report["alquileres"]} == {
                "paid-rental",
                "void-rental",
            }
            assert next(
                a for a in report["alquileres"] if a["id"] == "void-rental"
            )["anulado"] is True
            assert any(
                p["id"] == "void-payment" and p["anulado"] is True
                for p in report["pagos"]
            )
            assert report["totales"]["pagos"] == 25
            assert report["totales"]["alquileres"] == 60
            assert report["totales"]["validos"] == 85
            assert report["totales"]["anulados"] == 48
            assert report["totales"]["count_validos"] == 2
            assert report["totales"]["count_anulados"] == 2
            by_user = await client.get(f"{API}/reportes", params={
                **params, "created_by": "user-Administrador-office-a",
            })
            assert by_user.json()["totales"]["validos"] == 85
            empty_user = await client.get(f"{API}/reportes", params={**params, "created_by": "other"})
            assert empty_user.json()["totales"]["validos"] == 0

            search = {"fecha_desde": day, "fecha_hasta": day}
            found = await client.get(f"{API}/comprobantes", params=search)
            assert found.status_code == 200, found.text
            assert found.json()["total"] == 4
            assert {p["origen"] for p in found.json()["items"]} == {"alquiler", "pago"}
            matched_user = await client.get(f"{API}/comprobantes", params={
                **search, "created_by": "user-Administrador-office-a",
            })
            assert matched_user.json()["total"] == 4
            student = await client.get(f"{API}/comprobantes", params={
                **search, "q": f"RTA-00001 / {year}",
            })
            assert [p["id"] for p in student.json()["items"]] == ["student-payment"]
            for term in (f"RTA-00003 / {year}", "Cliente Alquiler", "Sala Mayor"):
                result = await client.get(f"{API}/comprobantes", params={**search, "q": term})
                expected = (
                    {"paid-rental"}
                    if term == f"RTA-00003 / {year}"
                    else {"paid-rental", "void-rental"}
                )
                assert {p["id"] for p in result.json()["items"]} == expected
            typed = await client.get(f"{API}/comprobantes", params={**search, "id_tipo_pago": "any"})
            assert typed.json()["total"] == 0
            other_user = await client.get(f"{API}/comprobantes", params={**search, "created_by": "other"})
            assert other_user.json()["total"] == 0
            page = await client.get(f"{API}/comprobantes", params={**search, "tam": 1, "pag": 2})
            assert page.json()["total"] == 4 and page.json()["pages"] == 4
            after = await client.get(f"{API}/comprobantes", params={"fecha_desde": next_day, "fecha_hasta": next_day})
            assert [p["id"] for p in after.json()["items"]] == ["other-date-rental"]
        async with await _client(_actor("SuperAdmin", "office-a")) as admin:
            all_offices = await admin.get(f"{API}/reportes", params=params)
            assert all_offices.json()["totales"]["alquileres"] == 120
            office_b = await admin.get(f"{API}/reportes", params={**params, "office_id": "office-b"})
            assert office_b.json()["totales"]["alquileres"] == 60
        async with await _client(_actor("Caja", "office-a")) as caja:
            denied = await caja.get(f"{API}/comprobantes", params={"office_id": "office-b"})
            assert denied.status_code in (403, 404)

    state["loop"].run_until_complete(scenario())