from datetime import timedelta

from test_rentals_integration import (
    API,
    _actor,
    _client,
    mongo_rental_api,
    server,
)


def test_payment_annulment_respects_creator_issue_date_and_office(mongo_rental_api):
    state = mongo_rental_api
    today = server._current_bolivia_date()
    yesterday = (today - timedelta(days=1)).isoformat()
    today = today.isoformat()

    async def scenario():
        db = state["db"]
        await db.pagos.insert_many([
            {
                "id": "cashier-own-today",
                "office_id": "office-a",
                "fecha_pago": today,
                "created_by": "user-Caja-office-a",
                "estado": "emitido",
                "anulado": False,
            },
            {
                "id": "cashier-own-yesterday",
                "office_id": "office-a",
                "fecha_pago": yesterday,
                "created_by": "user-Caja-office-a",
                "estado": "emitido",
                "anulado": False,
            },
            {
                "id": "cashier-other-owner",
                "office_id": "office-a",
                "fecha_pago": today,
                "created_by": "another-cashier",
                "estado": "emitido",
                "anulado": False,
            },
            {
                "id": "admin-old-payment",
                "office_id": "office-a",
                "fecha_pago": yesterday,
                "created_by": "user-Administrador-office-a",
                "estado": "emitido",
                "anulado": False,
            },
            {
                "id": "other-office-payment",
                "office_id": "office-b",
                "fecha_pago": yesterday,
                "created_by": "user-Administrador-office-b",
                "estado": "emitido",
                "anulado": False,
            },
        ])

        async with await _client(_actor("Caja", "office-a")) as cashier:
            own_today = await cashier.post(
                f"{API}/pagos/cashier-own-today/anular"
            )
            own_yesterday = await cashier.post(
                f"{API}/pagos/cashier-own-yesterday/anular"
            )
            another_user = await cashier.post(
                f"{API}/pagos/cashier-other-owner/anular"
            )
            assert own_today.status_code == 200, own_today.text
            assert own_yesterday.status_code == 403
            assert another_user.status_code == 403

        async with await _client(_actor("Administrador", "office-a")) as admin:
            old_own_office = await admin.post(
                f"{API}/pagos/admin-old-payment/anular"
            )
            other_office = await admin.post(
                f"{API}/pagos/other-office-payment/anular"
            )
            assert old_own_office.status_code == 200, old_own_office.text
            assert other_office.status_code == 404

        async with await _client(_actor("SuperAdmin", "office-a")) as superadmin:
            other_office = await superadmin.post(
                f"{API}/pagos/other-office-payment/anular"
            )
            assert other_office.status_code == 200, other_office.text

    state["loop"].run_until_complete(scenario())