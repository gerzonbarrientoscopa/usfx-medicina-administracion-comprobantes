"""Mongo-backed rental API tests isolated to a unique disposable database."""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ServerSelectionTimeoutError

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "rental_integration_tests")
os.environ.setdefault("JWT_SECRET", "rental-integration-test-secret")
os.environ.setdefault("ADMIN_PASSWORD", "rental-integration-test-password")
os.environ.setdefault("ADMIN_NAME", "Rental Integration Admin")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server


API = "/api"


def _monday():
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7)


@pytest.fixture
def mongo_rental_api():
    state = {}
    loop = asyncio.new_event_loop()

    async def initialize():
        client = AsyncIOMotorClient(server.MONGO_URL, serverSelectionTimeoutMS=2500)
        try:
            await client.admin.command("ping")
        except ServerSelectionTimeoutError:
            client.close()
            pytest.skip("A MongoDB server is required for rental integration tests.")

        db_name = f"rental_integration_{uuid.uuid4().hex}"
        db = client[db_name]
        state.update(client=client, db=db, db_name=db_name, prior_db=server.db)
        server.db = db
        await db.oficinas.create_index("id", unique=True)
        await db.ambientes.create_index("id", unique=True)
        await db.tarifas_ambientes.create_index("id", unique=True)
        await db.alquileres.create_index("id", unique=True)
        await db.alquileres.create_index(
            [("office_id", 1), ("gestion", 1), ("cod_comprobante", 1)],
            unique=True,
            partialFilterExpression={"estado": "pagado"},
        )
        await db.personas.create_index("id", unique=True)
        await db.personas.create_index("ci_key", unique=True)
        await db.estudiantes.create_index("id", unique=True)

        office_a, office_b = "office-a", "office-b"
        for office_id, prefix in ((office_a, "RTA"), (office_b, "RTB")):
            await db.oficinas.insert_one({
                "id": office_id, "nombre": f"Integration {office_id}",
                "prefijo_comprobante": prefix, "suboficina": "", "activa": True,
            })
        monday = _monday().isoformat()
        ambientes = []
        for office_id, ambiente_id in ((office_a, "room-a"), (office_b, "room-b")):
            ambiente = {
                "id": ambiente_id, "office_id": office_id, "nombre": f"Room {office_id}",
                "horarios": [
                    {"dia": "lunes", "desde": "09:00", "hasta": "12:00"},
                    {"dia": "lunes", "desde": "13:00", "hasta": "17:00"},
                ],
            }
            ambientes.append(ambiente)
            await db.ambientes.insert_one(ambiente)
        await db.personas.insert_one({
            "id": "person-a", "ci": "CI-P-001", "ci_key": "ci-p-001",
            "nombre": "Persona Rental",
        })
        await db.estudiantes.insert_one({
            "id": "student-b", "office_id": office_b, "ci": "CI-S-001",
            "cu": "CU-001", "nombre": "Estudiante Rental", "gestion": 2026,
        })
        state.update(
            office_a=office_a, office_b=office_b, monday=monday,
            ambiente_a=ambientes[0]["id"], ambiente_b=ambientes[1]["id"],
        )

    try:
        loop.run_until_complete(initialize())
    except BaseException:
        if state.get("db_name"):
            loop.run_until_complete(state["client"].drop_database(state["db_name"]))
        if state.get("client"):
            state["client"].close()
        loop.close()
        raise
    state["loop"] = loop
    try:
        yield state
    finally:
        async def cleanup():
            server.app.dependency_overrides.clear()
            server.db = state["prior_db"]
            await state["client"].drop_database(state["db_name"])
            state["client"].close()

        loop.run_until_complete(cleanup())
        loop.close()


def _actor(role="Administrador", office="office-a"):
    return {"id": f"user-{role}-{office}", "rol": role, "office_id": office, "nombre": "Test"}


async def _client(actor):
    server.app.dependency_overrides[server.get_current_user] = lambda: actor
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://rental-test",
    )


def _tariff_payload(ambiente_id, **overrides):
    payload = {
        "ambiente_id": ambiente_id, "nombre": "Hourly room",
        "modalidad": "hora", "monto": "60.00", "descripcion": "Integration tariff",
    }
    payload.update(overrides)
    return payload


def _rental_payload(ambiente_id, tarifa_id, fecha, start="09:00", end="10:00", **overrides):
    payload = {
        "ambiente_id": ambiente_id, "tarifa_id": tarifa_id, "fecha": fecha,
        "desde": start, "hasta": end, "cliente_tipo": "persona",
        "cliente_id": "person-a", "cobrar_ahora": False,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def empty_startup_database():
    loop = asyncio.new_event_loop()
    state = {}
    client = AsyncIOMotorClient(server.MONGO_URL, serverSelectionTimeoutMS=2500)

    async def initialize():
        try:
            await client.admin.command("ping")
        except ServerSelectionTimeoutError:
            client.close()
            pytest.skip("A MongoDB server is required for rental integration tests.")
        name = f"rental_startup_{uuid.uuid4().hex}"
        state.update(client=client, name=name, prior_db=server.db, db=client[name])
        server.db = state["db"]

    try:
        loop.run_until_complete(initialize())
    except BaseException:
        client.close()
        loop.close()
        raise
    state["loop"] = loop
    try:
        yield state
    finally:
        async def cleanup():
            server.db = state["prior_db"]
            await client.drop_database(state["name"])
            client.close()
        loop.run_until_complete(cleanup())
        loop.close()


def test_tariff_crud_and_validation_in_mongo(mongo_rental_api):
    async def run():
        async with await _client(_actor()) as client:
            created = await client.post(f"{API}/tarifas-ambientes", json=_tariff_payload(mongo_rental_api["ambiente_a"]))
            assert created.status_code == 201, created.text
            tariff = created.json()
            assert tariff["office_id"] == mongo_rental_api["office_a"]
            assert tariff["monto"] == 60.0

            listed = await client.get(f"{API}/tarifas-ambientes", params={"ambiente_id": mongo_rental_api["ambiente_a"]})
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()] == [tariff["id"]]

            updated = await client.put(
                f'{API}/tarifas-ambientes/{tariff["id"]}',
                json=_tariff_payload(mongo_rental_api["ambiente_a"], nombre="Updated", monto="75.25"),
            )
            assert updated.status_code == 200
            assert updated.json()["nombre"] == "Updated"
            assert updated.json()["monto"] == 75.25

            bad_fixed = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"], modalidad="manana"),
            )
            assert bad_fixed.status_code == 422
            bad_hourly = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"], desde="09:00", hasta="10:00"),
            )
            assert bad_hourly.status_code == 422
            bad_amount = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"], monto="1.001"),
            )
            assert bad_amount.status_code == 422

            caja = await _client(_actor("Caja"))
            async with caja:
                readable_environments = await caja.get(
                    f"{API}/ambientes", params={"office_id": mongo_rental_api["office_a"]}
                )
                assert readable_environments.status_code == 200
                assert len(readable_environments.json()["items"]) == 1
                other_office_environments = await caja.get(
                    f"{API}/ambientes", params={"office_id": mongo_rental_api["office_b"]}
                )
                assert other_office_environments.status_code == 403
                environment_write = await caja.post(
                    f"{API}/ambientes",
                    json={"nombre": "Caja cannot create", "office_id": mongo_rental_api["office_a"], "horarios": []},
                )
                assert environment_write.status_code == 403
                forbidden_write = await caja.post(
                    f"{API}/tarifas-ambientes",
                    json=_tariff_payload(mongo_rental_api["ambiente_a"]),
                )
                assert forbidden_write.status_code == 403
            server.app.dependency_overrides[server.get_current_user] = lambda: _actor()

            deleted = await client.delete(f'{API}/tarifas-ambientes/{tariff["id"]}')
            assert deleted.status_code == 200
            assert await mongo_rental_api["db"].tarifas_ambientes.find_one({"id": tariff["id"]}) is None

    mongo_rental_api["loop"].run_until_complete(run())


def test_booking_clients_schedule_overlap_adjacency_and_concurrency(mongo_rental_api):
    async def run():
        async with await _client(_actor()) as client:
            tariff_response = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            assert tariff_response.status_code == 201, tariff_response.text
            tariff_id = tariff_response.json()["id"]
            fecha = mongo_rental_api["monday"]

            gap = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(mongo_rental_api["ambiente_a"], tariff_id, fecha, "11:30", "13:30"),
            )
            assert gap.status_code == 400

            person_booking = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(mongo_rental_api["ambiente_a"], tariff_id, fecha, "09:00", "10:00"),
            )
            assert person_booking.status_code == 201, person_booking.text
            assert person_booking.json()["cliente_tipo"] == "persona"
            assert person_booking.json()["cliente_nombre"] == "Persona Rental"

            adjacent_student = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff_id, fecha, "10:00", "11:00",
                    cliente_tipo="estudiante", cliente_id="student-b",
                ),
            )
            assert adjacent_student.status_code == 400
            wrong_proof = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff_id, fecha, "10:00", "11:00",
                    cliente_tipo="estudiante", cliente_id="student-b",
                    cliente_documento="not-the-student-document",
                ),
            )
            assert wrong_proof.status_code == 400
            adjacent_student = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff_id, fecha, "10:00", "11:00",
                    cliente_tipo="estudiante", cliente_id="student-b",
                    cliente_documento=" ci-s-001 ",
                ),
            )
            assert adjacent_student.status_code == 201, adjacent_student.text
            assert adjacent_student.json()["cliente_tipo"] == "estudiante"
            assert adjacent_student.json()["cliente_cu"] == "CU-001"

            overlap = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(mongo_rental_api["ambiente_a"], tariff_id, fecha, "09:30", "10:30"),
            )
            assert overlap.status_code == 409

            contender_payload = _rental_payload(
                mongo_rental_api["ambiente_a"], tariff_id, fecha, "14:00", "15:00",
            )
            async with await _client(_actor("Caja")) as concurrent_client:
                results = await asyncio.gather(
                    client.post(f"{API}/alquileres", json=contender_payload),
                    concurrent_client.post(f"{API}/alquileres", json=contender_payload),
                )
            assert sorted(result.status_code for result in results) == [201, 409]
            assert await mongo_rental_api["db"].alquileres.count_documents({
                "ambiente_id": mongo_rental_api["ambiente_a"], "fecha": fecha,
                "tramos.desde": "14:00",
            }) == 1

    mongo_rental_api["loop"].run_until_complete(run())


def test_reserve_payment_immediate_payment_cancel_and_counter(mongo_rental_api):
    async def run():
        async with await _client(_actor()) as client:
            tariff_response = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            assert tariff_response.status_code == 201
            tariff_id = tariff_response.json()["id"]
            server.app.dependency_overrides[server.get_current_user] = lambda: _actor("Caja")
            fecha = mongo_rental_api["monday"]

            reserved_response = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(mongo_rental_api["ambiente_a"], tariff_id, fecha),
            )
            assert reserved_response.status_code == 201, reserved_response.text
            reserved = reserved_response.json()
            assert reserved["estado"] == "reservado"
            assert reserved["cod_comprobante"] is None
            assert await mongo_rental_api["db"].contadores.find_one({
                "_id": f'comprobante_{mongo_rental_api["office_a"]}_{datetime.now(timezone.utc).year}'
            }) is None

            paid_response = await client.post(f'{API}/alquileres/{reserved["id"]}/pagar')
            assert paid_response.status_code == 200, paid_response.text
            paid = paid_response.json()
            assert paid["estado"] == "pagado"
            code = paid["cod_comprobante"]
            repeated = await client.post(f'{API}/alquileres/{reserved["id"]}/pagar')
            assert repeated.status_code == 200
            assert repeated.json()["cod_comprobante"] == code

            immediate_response = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff_id, fecha, "10:00", "11:00",
                    cobrar_ahora=True,
                ),
            )
            assert immediate_response.status_code == 201, immediate_response.text
            immediate = immediate_response.json()
            assert immediate["estado"] == "pagado"
            assert int(immediate["cod_comprobante"]) == int(code) + 1

            cancellable_response = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(mongo_rental_api["ambiente_a"], tariff_id, fecha, "11:00", "12:00"),
            )
            assert cancellable_response.status_code == 201
            cancellable = cancellable_response.json()
            cancelled = await client.post(f'{API}/alquileres/{cancellable["id"]}/cancelar')
            assert cancelled.status_code == 200
            assert cancelled.json()["estado"] == "cancelado"
            cancellation_retry = await client.post(f'{API}/alquileres/{cancellable["id"]}/cancelar')
            assert cancellation_retry.status_code == 200
            assert cancellation_retry.json()["estado"] == "cancelado"
            reused_slot = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(mongo_rental_api["ambiente_a"], tariff_id, fecha, "11:00", "12:00"),
            )
            assert reused_slot.status_code == 201, reused_slot.text
            assert reused_slot.json()["estado"] == "reservado"

    mongo_rental_api["loop"].run_until_complete(run())


def test_comprobante_search_includes_rental_office_suboffice(mongo_rental_api):
    async def run():
        db = mongo_rental_api["db"]
        await db.oficinas.update_one(
            {"id": mongo_rental_api["office_a"]},
            {"$set": {"suboficina": "Suboficina de prueba"}},
        )
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            assert tariff.status_code == 201, tariff.text
            paid = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], cobrar_ahora=True,
                ),
            )
            assert paid.status_code == 201, paid.text
            response = await client.get(
                f"{API}/comprobantes", params={"q": paid.json()["cod_comprobante"]}
            )
            assert response.status_code == 200, response.text
            rental_receipt = next(
                item for item in response.json()["items"]
                if item.get("origen") == "alquiler"
            )
            assert rental_receipt["suboficina"] == "Suboficina de prueba"

    mongo_rental_api["loop"].run_until_complete(run())


def test_rentals_and_tariffs_reject_cross_office_access(mongo_rental_api):
    async def run():
        async with await _client(_actor()) as client:
            other_tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_b"]),
            )
            assert other_tariff.status_code == 403

            other_tariff_in_db = {
                "id": "tariff-b", "ambiente_id": mongo_rental_api["ambiente_b"],
                "office_id": mongo_rental_api["office_b"], "nombre": "Other office",
                "modalidad": "hora", "monto": 60.0, "descripcion": "",
                "desde": None, "hasta": None,
            }
            await mongo_rental_api["db"].tarifas_ambientes.insert_one(other_tariff_in_db)
            cross_read = await client.get(
                f"{API}/tarifas-ambientes",
                params={"ambiente_id": mongo_rental_api["ambiente_b"]},
            )
            assert cross_read.status_code == 403
            cross_booking = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_b"], "tariff-b", mongo_rental_api["monday"],
                ),
            )
            assert cross_booking.status_code == 403

            super_admin = await _client(_actor("SuperAdmin", None))
            async with super_admin:
                allowed = await super_admin.get(
                    f"{API}/tarifas-ambientes",
                    params={"ambiente_id": mongo_rental_api["ambiente_b"]},
                )
                assert allowed.status_code == 200

    mongo_rental_api["loop"].run_until_complete(run())


def test_person_and_student_ci_are_mutually_exclusive(mongo_rental_api):
    async def run():
        async with await _client(_actor()) as client:
            duplicate_person = await client.post(
                f"{API}/personas", json={"ci": " ci-s-001 ", "nombre": "Duplicate student CI"}
            )
            assert duplicate_person.status_code == 400

            persona = await client.post(
                f"{API}/personas", json={"ci": "CI-P-001", "nombre": "Existing persona"}
            )
            assert persona.status_code == 400  # seeded global Persona CI
            persona = await client.post(
                f"{API}/personas", json={"ci": "CI-PERSON-2", "nombre": "Existing persona"}
            )
            assert persona.status_code == 201, persona.text
            persona_update = await client.put(
                f'{API}/personas/{persona.json()["id"]}',
                json={"ci": " ci-s-001 ", "nombre": "Changed to student CI"},
            )
            assert persona_update.status_code == 400

            student_payload = {
                "ci": "ci-p-001", "cu": "CU-PERSON-DUP", "nombre": "Duplicate persona CI",
                "gestion": 2026, "office_id": mongo_rental_api["office_a"],
            }
            student_create = await client.post(f"{API}/estudiantes", json=student_payload)
            assert student_create.status_code == 400

            allowed_student = await client.post(
                f"{API}/estudiantes",
                json={**student_payload, "ci": "CI-STUDENT-UPDATE", "cu": "CU-STUDENT-UPDATE"},
            )
            assert allowed_student.status_code == 201, allowed_student.text
            student_update = await client.put(
                f'{API}/estudiantes/{allowed_student.json()["id"]}',
                json={**student_payload, "cu": "CU-STUDENT-UPDATE"},
            )
            assert student_update.status_code == 400

    mongo_rental_api["loop"].run_until_complete(run())


def test_customer_search_limits_cross_office_students_to_exact_identifiers(mongo_rental_api):
    async def run():
        await mongo_rental_api["db"].estudiantes.insert_one({
            "id": "student-local-search", "office_id": mongo_rental_api["office_a"],
            "ci": "LOCAL-CI-123", "cu": "LOCAL-CU-123",
            "nombre": "Unique Local Learner", "gestion": 2026,
        })
        async with await _client(_actor()) as client:
            partial = await client.get(f"{API}/alquileres/clientes", params={"q": "Learner"})
            assert partial.status_code == 200
            partial_students = [result for result in partial.json() if result["tipo"] == "estudiante"]
            assert [result["id"] for result in partial_students] == ["student-local-search"]

            partial_cross = await client.get(f"{API}/alquileres/clientes", params={"q": "Rental"})
            assert all(
                result["id"] != "student-b"
                for result in partial_cross.json()
                if result["tipo"] == "estudiante"
            )
            short_cross = await client.get(f"{API}/alquileres/clientes", params={"q": "CI"})
            assert all(result["id"] != "student-b" for result in short_cross.json())

            exact_ci = await client.get(f"{API}/alquileres/clientes", params={"q": "ci-s-001"})
            student_hit = next(result for result in exact_ci.json() if result["id"] == "student-b")
            assert student_hit["tipo"] == "estudiante"
            assert student_hit["office_nombre"] == "Integration office-b"
            assert "office_id" not in student_hit

            exact_cu = await client.get(f"{API}/alquileres/clientes", params={"q": "CU-001"})
            assert any(result["id"] == "student-b" for result in exact_cu.json())

        async with await _client(_actor("SuperAdmin", None)) as super_client:
            global_partial = await super_client.get(
                f"{API}/alquileres/clientes", params={"q": "Rental"}
            )
            assert any(result["id"] == "student-b" for result in global_partial.json())

    mongo_rental_api["loop"].run_until_complete(run())


def test_startup_reconciliation_repairs_stranded_rentals_and_occupancy(mongo_rental_api):
    async def run():
        db = mongo_rental_api["db"]
        await db.alquileres.insert_many([
            {
                "id": "repair-processing", "estado": "procesando",
                "processing_lease_until": server.iso(
                    datetime.now(timezone.utc) - timedelta(seconds=5)
                ),
            },
            {
                "id": "repair-fresh-processing", "estado": "procesando",
                "processing_lease_until": server.iso(
                    datetime.now(timezone.utc) + timedelta(seconds=90)
                ),
                "payment_token": "currently-active-worker",
            },
            {"id": "repair-paid", "estado": "pagado"},
            {"id": "repair-canceled", "estado": "cancelado"},
        ])
        occupancy_id = f'{mongo_rental_api["ambiente_a"]}_{mongo_rental_api["monday"]}'
        await db.alquiler_ocupacion.insert_one({
            "_id": occupancy_id,
            "ambiente_id": mongo_rental_api["ambiente_a"],
            "fecha": mongo_rental_api["monday"],
            "intervals": [
                {"rental_id": "repair-processing", "start": 540, "end": 600},
                {"rental_id": "repair-paid", "start": 600, "end": 660},
                {"rental_id": "repair-fresh-processing", "start": 660, "end": 720},
                {"rental_id": "repair-canceled", "start": 720, "end": 780},
                {
                    "rental_id": "rental-record-missing", "start": 780, "end": 840,
                    "claimed_at": server.iso(datetime.now(timezone.utc) - timedelta(seconds=300)),
                },
            ],
        })

        await server.reconcile_rental_occupancy()
        processing = await db.alquileres.find_one({"id": "repair-processing"})
        assert processing["estado"] == "reservado"
        fresh_processing = await db.alquileres.find_one({"id": "repair-fresh-processing"})
        assert fresh_processing["estado"] == "procesando"
        slots = await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
        assert {interval["rental_id"] for interval in slots["intervals"]} == {
            "repair-processing", "repair-paid", "repair-fresh-processing",
        }
        paid = await db.alquileres.find_one({"id": "repair-paid"})
        assert paid["estado"] == "pagado"

    mongo_rental_api["loop"].run_until_complete(run())


def test_booking_requires_active_office(mongo_rental_api):
    async def run():
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            assert tariff.status_code == 201
            await mongo_rental_api["db"].oficinas.update_one(
                {"id": mongo_rental_api["office_a"]}, {"$set": {"activa": False}}
            )
            response = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"],
                ),
            )
            assert response.status_code == 404
            assert await mongo_rental_api["db"].alquileres.count_documents({}) == 0
            assert await mongo_rental_api["db"].alquiler_ocupacion.count_documents({}) == 0

    mongo_rental_api["loop"].run_until_complete(run())


def test_full_startup_succeeds_on_unique_empty_database(empty_startup_database):
    async def run():
        await server.startup()
        assert "rental_receipt_per_office_year" in await empty_startup_database["db"].alquileres.index_information()
        assert await empty_startup_database["db"].usuarios.find_one({"email": server.SUPER_ADMIN_EMAIL})

    empty_startup_database["loop"].run_until_complete(run())


def test_startup_succeeds_after_canceled_room_is_deleted(empty_startup_database):
    async def run():
        db = empty_startup_database["db"]
        await server.startup()
        await db.oficinas.insert_one({
            "id": "office-a", "nombre": "Startup Office", "nombre_key": "startup office",
            "prefijo_comprobante": "STA", "suboficina": "", "activa": True,
        })
        await db.ambientes.insert_one({
            "id": "room-a", "office_id": "office-a", "nombre": "Startup Room",
            "nombre_key": "startup room",
            "horarios": [{"dia": "lunes", "desde": "09:00", "hasta": "12:00"}],
        })
        await db.personas.insert_one({
            "id": "person-a", "ci": "STARTUP-CI", "ci_key": "startup-ci",
            "nombre": "Startup Person",
        })
        fecha = _monday().isoformat()
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload("room-a"),
            )
            assert tariff.status_code == 201
            booking = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    "room-a", tariff.json()["id"], fecha,
                ),
            )
            assert booking.status_code == 201, booking.text
            canceled = await client.post(f'{API}/alquileres/{booking.json()["id"]}/cancelar')
            assert canceled.status_code == 200

            occupancy_id = f"room-a_{fecha}"
            assert await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
            tariff_deleted = await client.delete(f'{API}/tarifas-ambientes/{tariff.json()["id"]}')
            assert tariff_deleted.status_code == 200
            room_deleted = await client.delete(f"{API}/ambientes/room-a")
            assert room_deleted.status_code == 200, room_deleted.text
            assert await db.alquiler_ocupacion.find_one({"_id": occupancy_id}) is None

            # Legacy orphan records for deleted rooms must not make startup fail.
            await db.alquiler_ocupacion.insert_one({
                "_id": "removed-room_2030-01-07",
                "intervals": [],
            })
            await server.startup()
            assert await db.alquiler_ocupacion.find_one({"_id": "removed-room_2030-01-07"})

    empty_startup_database["loop"].run_until_complete(run())


def test_schedule_update_and_booking_are_serialized_by_room_lease(mongo_rental_api, monkeypatch):
    async def run():
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            assert tariff.status_code == 201
            entered = asyncio.Event()
            continue_update = asyncio.Event()
            original_update = server._update_ambiente_under_lease

            async def paused_update(ambiente_id, body, user, lease_owner):
                entered.set()
                await continue_update.wait()
                return await original_update(ambiente_id, body, user, lease_owner)

            monkeypatch.setattr(server, "_update_ambiente_under_lease", paused_update)
            schedule = [{
                "dia": "lunes", "desde": "10:00", "hasta": "12:00",
            }]
            update_task = asyncio.create_task(client.put(
                f'{API}/ambientes/{mongo_rental_api["ambiente_a"]}',
                json={"nombre": "Room office-a", "horarios": schedule},
            ))
            await asyncio.wait_for(entered.wait(), timeout=5)

            concurrent_booking = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], "09:00", "10:00",
                ),
            )
            assert concurrent_booking.status_code == 409
            continue_update.set()
            schedule_response = await update_task
            assert schedule_response.status_code == 200, schedule_response.text

            rejected_after_edit = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], "09:00", "10:00",
                ),
            )
            assert rejected_after_edit.status_code == 400
            assert await mongo_rental_api["db"].alquileres.count_documents({}) == 0

            valid_booking = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], "10:00", "11:00",
                ),
            )
            assert valid_booking.status_code == 201
            invalidating_edit = await client.put(
                f'{API}/ambientes/{mongo_rental_api["ambiente_a"]}',
                json={
                    "nombre": "Room office-a",
                    "horarios": [{"dia": "lunes", "desde": "11:00", "hasta": "12:00"}],
                },
            )
            assert invalidating_edit.status_code == 400
            current_room = await mongo_rental_api["db"].ambientes.find_one(
                {"id": mongo_rental_api["ambiente_a"]}
            )
            assert current_room["horarios"] == schedule

    mongo_rental_api["loop"].run_until_complete(run())


def test_expired_room_lease_owner_cannot_commit_after_takeover(mongo_rental_api, monkeypatch):
    async def run():
        db = mongo_rental_api["db"]
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            original_claim = server._claim_rental_intervals
            taken_over = {"done": False}

            async def expire_and_take_over(rental):
                await original_claim(rental)
                if taken_over["done"]:
                    return
                taken_over["done"] = True
                await db.ambientes.update_one(
                    {"id": mongo_rental_api["ambiente_a"]},
                    {"$set": {
                        "_room_lease.lease_until": datetime.now(timezone.utc) - timedelta(seconds=1),
                    }},
                )
                async with server._ambiente_lease(mongo_rental_api["ambiente_a"]):
                    await db.ambientes.update_one(
                        {"id": mongo_rental_api["ambiente_a"]},
                        {"$set": {"horarios": [{"dia": "lunes", "desde": "10:00", "hasta": "12:00"}]}},
                    )

            monkeypatch.setattr(server, "_claim_rental_intervals", expire_and_take_over)
            response = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], "09:00", "10:00",
                ),
            )
            assert response.status_code == 409
            assert await db.alquileres.count_documents(
                {"estado": {"$in": ["confirmando", "reservado", "procesando", "pagado"]}}
            ) == 0
            occupancy_id = f'{mongo_rental_api["ambiente_a"]}_{mongo_rental_api["monday"]}'
            occupancy = await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
            assert occupancy["intervals"] == []

    mongo_rental_api["loop"].run_until_complete(run())


def test_paused_provisional_insert_cancels_after_schedule_change_and_competing_booking(mongo_rental_api, monkeypatch):
    async def run():
        db = mongo_rental_api["db"]
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            entered_insert = asyncio.Event()
            resume_insert = asyncio.Event()
            original_insert = server._insert_rental_provisional
            did_pause = {"value": False}

            async def pause_first_insert(rental):
                if not did_pause["value"]:
                    did_pause["value"] = True
                    entered_insert.set()
                    await resume_insert.wait()
                return await original_insert(rental)

            monkeypatch.setattr(server, "_insert_rental_provisional", pause_first_insert)
            stale_request = asyncio.create_task(client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], "09:00", "10:00",
                ),
            ))
            await asyncio.wait_for(entered_insert.wait(), timeout=5)

            occupancy_id = f'{mongo_rental_api["ambiente_a"]}_{mongo_rental_api["monday"]}'
            stale_claim = await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
            provisional_id = stale_claim["intervals"][0]["rental_id"]
            await db.alquiler_ocupacion.update_one(
                {"_id": occupancy_id},
                {"$set": {
                    "intervals.$[claim].claimed_at": server.iso(
                        datetime.now(timezone.utc) - timedelta(seconds=300)
                    ),
                }},
                array_filters=[{"claim.rental_id": provisional_id}],
            )
            await db.ambientes.update_one(
                {"id": mongo_rental_api["ambiente_a"]},
                {"$set": {
                    "_room_lease.lease_until": datetime.now(timezone.utc) - timedelta(seconds=1),
                }},
            )

            edit = await client.put(
                f'{API}/ambientes/{mongo_rental_api["ambiente_a"]}',
                json={
                    "nombre": "Room office-a",
                    "horarios": [{"dia": "lunes", "desde": "10:00", "hasta": "12:00"}],
                },
            )
            assert edit.status_code == 200, edit.text
            competing = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], "10:00", "11:00",
                ),
            )
            assert competing.status_code == 201, competing.text

            resume_insert.set()
            stale_response = await stale_request
            assert stale_response.status_code == 409
            stale_rental = await db.alquileres.find_one({"id": provisional_id})
            assert stale_rental["estado"] == "cancelado"
            competing_rental = await db.alquileres.find_one({"id": competing.json()["id"]})
            assert competing_rental["estado"] == "reservado"
            occupancy = await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
            assert {interval["rental_id"] for interval in occupancy["intervals"]} == {
                competing.json()["id"],
            }
            listed = await client.get(
                f"{API}/alquileres",
                params={
                    "ambiente_id": mongo_rental_api["ambiente_a"],
                    "fecha_desde": mongo_rental_api["monday"],
                    "fecha_hasta": mongo_rental_api["monday"],
                },
            )
            assert listed.status_code == 200
            assert all(row["estado"] != "confirmando" for row in listed.json())

    mongo_rental_api["loop"].run_until_complete(run())


def test_stale_provisional_reaper_and_final_confirmation_resolve_by_cas(mongo_rental_api, monkeypatch):
    async def run():
        db = mongo_rental_api["db"]
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            entered_confirmation = asyncio.Event()
            resume_confirmation = asyncio.Event()
            original_confirm = server._confirm_rental_provisional
            paused = {"value": False}

            async def pause_confirmation(rental_id, confirmation_started_at):
                if not paused["value"]:
                    paused["value"] = True
                    entered_confirmation.set()
                    await resume_confirmation.wait()
                return await original_confirm(rental_id, confirmation_started_at)

            monkeypatch.setattr(server, "_confirm_rental_provisional", pause_confirmation)
            create_task = asyncio.create_task(client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"],
                ),
            ))
            await asyncio.wait_for(entered_confirmation.wait(), timeout=5)
            occupancy_id = f'{mongo_rental_api["ambiente_a"]}_{mongo_rental_api["monday"]}'
            occupancy = await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
            provisional_id = occupancy["intervals"][0]["rental_id"]
            await db.alquileres.update_one(
                {"id": provisional_id, "estado": "confirmando"},
                {"$set": {
                    "confirmation_started_at": server.iso(
                        datetime.now(timezone.utc) - timedelta(seconds=300)
                    ),
                }},
            )
            await db.ambientes.update_one(
                {"id": mongo_rental_api["ambiente_a"]},
                {"$set": {
                    "_room_lease.lease_until": datetime.now(timezone.utc) - timedelta(seconds=1),
                }},
            )

            await server.reconcile_rental_occupancy()
            canceled = await db.alquileres.find_one({"id": provisional_id})
            assert canceled["estado"] == "cancelado"
            resume_confirmation.set()
            response = await create_task
            assert response.status_code == 409
            occupancy = await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
            assert occupancy["intervals"] == []
            assert await db.alquileres.count_documents({"estado": "reservado"}) == 0

    mongo_rental_api["loop"].run_until_complete(run())


def test_unknown_confirmation_outcome_preserves_active_occupancy(mongo_rental_api, monkeypatch):
    async def run():
        db = mongo_rental_api["db"]
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            original_confirm = server._confirm_rental_provisional

            async def confirm_then_raise(rental_id, confirmation_started_at):
                result = await original_confirm(rental_id, confirmation_started_at)
                assert result.modified_count == 1
                raise RuntimeError("simulated unknown write outcome")

            monkeypatch.setattr(server, "_confirm_rental_provisional", confirm_then_raise)
            response = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"],
                ),
            )
            assert response.status_code == 500
            assert "reserva" in response.json()["detail"].lower()
            committed = await db.alquileres.find_one({"estado": "reservado"})
            assert committed is not None
            assert committed["id"] in response.json()["detail"]
            occupancy_id = f'{mongo_rental_api["ambiente_a"]}_{mongo_rental_api["monday"]}'
            occupancy = await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
            assert {item["rental_id"] for item in occupancy["intervals"]} == {committed["id"]}

            duplicate = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"],
                ),
            )
            assert duplicate.status_code == 409
            assert await db.alquileres.count_documents({"estado": "reservado"}) == 1

    mongo_rental_api["loop"].run_until_complete(run())


def test_expired_schedule_editor_cannot_overwrite_after_new_booking_wins(mongo_rental_api, monkeypatch):
    async def run():
        db = mongo_rental_api["db"]
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            entered = asyncio.Event()
            resume_editor = asyncio.Event()
            original_update = server._update_ambiente_under_lease

            async def paused_update(ambiente_id, body, user, lease_owner):
                entered.set()
                await resume_editor.wait()
                return await original_update(ambiente_id, body, user, lease_owner)

            monkeypatch.setattr(server, "_update_ambiente_under_lease", paused_update)
            edit_task = asyncio.create_task(client.put(
                f'{API}/ambientes/{mongo_rental_api["ambiente_a"]}',
                json={
                    "nombre": "Stale editor rename",
                    "horarios": [{"dia": "lunes", "desde": "09:00", "hasta": "12:00"}],
                },
            ))
            await asyncio.wait_for(entered.wait(), timeout=5)
            await db.ambientes.update_one(
                {"id": mongo_rental_api["ambiente_a"]},
                {"$set": {
                    "_room_lease.lease_until": datetime.now(timezone.utc) - timedelta(seconds=1),
                }},
            )
            booking = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], "10:00", "11:00",
                ),
            )
            assert booking.status_code == 201, booking.text
            resume_editor.set()
            edit_response = await edit_task
            assert edit_response.status_code == 409
            room = await db.ambientes.find_one({"id": mongo_rental_api["ambiente_a"]})
            assert room["nombre"] == "Room office-a"
            assert room["horarios"] == [
                {"dia": "lunes", "desde": "09:00", "hasta": "12:00"},
                {"dia": "lunes", "desde": "13:00", "hasta": "17:00"},
            ]

    mongo_rental_api["loop"].run_until_complete(run())


def test_later_claim_cleans_stale_occupancy_but_preserves_live_claims(mongo_rental_api):
    async def run():
        db = mongo_rental_api["db"]
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            assert tariff.status_code == 201
            occupancy_id = f'{mongo_rental_api["ambiente_a"]}_{mongo_rental_api["monday"]}'
            await db.alquiler_ocupacion.insert_one({
                "_id": occupancy_id,
                "ambiente_id": mongo_rental_api["ambiente_a"],
                "fecha": mongo_rental_api["monday"],
                "intervals": [
                    {
                        "rental_id": "stale-missing-booking", "start": 540, "end": 600,
                        "claimed_at": server.iso(datetime.now(timezone.utc) - timedelta(seconds=300)),
                    },
                    {
                        "rental_id": "fresh-inflight-booking", "start": 600, "end": 660,
                        "claimed_at": server.iso(datetime.now(timezone.utc)),
                    },
                ],
            })
            reclaimed = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"],
                ),
            )
            assert reclaimed.status_code == 201, reclaimed.text
            occupancy = await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
            assert {interval["rental_id"] for interval in occupancy["intervals"]} == {
                "fresh-inflight-booking", reclaimed.json()["id"],
            }
            fresh_conflict = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], "10:00", "11:00",
                ),
            )
            assert fresh_conflict.status_code == 409

            blocked = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], "09:30", "10:30",
                ),
            )
            assert blocked.status_code == 409
            occupancy = await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
            assert {interval["rental_id"] for interval in occupancy["intervals"]} == {
                "fresh-inflight-booking", reclaimed.json()["id"],
            }

    mongo_rental_api["loop"].run_until_complete(run())


def test_reconciliation_pull_preserves_intervals_added_after_its_snapshot(mongo_rental_api, monkeypatch):
    async def run():
        db = mongo_rental_api["db"]
        occupancy_id = f'{mongo_rental_api["ambiente_a"]}_{mongo_rental_api["monday"]}'
        await db.alquileres.insert_one({"id": "active-rental-during-recovery", "estado": "reservado"})
        await db.alquiler_ocupacion.insert_one({
            "_id": occupancy_id,
            "ambiente_id": mongo_rental_api["ambiente_a"],
            "fecha": mongo_rental_api["monday"],
            "intervals": [
                {
                    "rental_id": "old-orphan", "start": 540, "end": 600,
                    "claimed_at": server.iso(datetime.now(timezone.utc) - timedelta(seconds=300)),
                },
                {"rental_id": "active-rental-during-recovery", "start": 600, "end": 660},
            ],
        })
        original_pull = server._pull_occupancy_rental_claim
        interleaved = {"done": False}

        async def append_during_pull(target_occupancy_id, stale_rental_id):
            if not interleaved["done"]:
                interleaved["done"] = True
                await db.alquiler_ocupacion.update_one(
                    {"_id": occupancy_id},
                    {"$push": {"intervals": {
                        "rental_id": "new-concurrent-claim", "start": 660, "end": 720,
                        "claimed_at": server.iso(datetime.now(timezone.utc)),
                    }}},
                )
            await original_pull(target_occupancy_id, stale_rental_id)

        monkeypatch.setattr(server, "_pull_occupancy_rental_claim", append_during_pull)
        await server.reconcile_rental_occupancy()
        remaining = await db.alquiler_ocupacion.find_one({"_id": occupancy_id})
        assert {slot["rental_id"] for slot in remaining["intervals"]} == {
            "active-rental-during-recovery", "new-concurrent-claim",
        }

    mongo_rental_api["loop"].run_until_complete(run())


def test_stale_payment_retries_recover_but_fresh_processing_is_protected(mongo_rental_api):
    async def run():
        db = mongo_rental_api["db"]
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            tariff_id = tariff.json()["id"]
            first = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff_id,
                    mongo_rental_api["monday"],
                ),
            )
            assert first.status_code == 201
            await db.alquileres.update_one(
                {"id": first.json()["id"]},
                {"$set": {
                    "estado": "procesando", "payment_token": "crashed-worker",
                    "processing_lease_until": server.iso(datetime.now(timezone.utc) - timedelta(seconds=1)),
                }},
            )
            recovered = await client.post(f'{API}/alquileres/{first.json()["id"]}/pagar')
            assert recovered.status_code == 200, recovered.text
            assert recovered.json()["estado"] == "pagado"

            second = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff_id,
                    mongo_rental_api["monday"], "10:00", "11:00",
                ),
            )
            assert second.status_code == 201
            await db.alquileres.update_one(
                {"id": second.json()["id"]},
                {"$set": {
                    "estado": "procesando", "payment_token": "fresh-worker",
                    "processing_lease_until": server.iso(datetime.now(timezone.utc) + timedelta(seconds=60)),
                }},
            )
            before = await db.contadores.find_one({
                "_id": f'comprobante_{mongo_rental_api["office_a"]}_{datetime.now(timezone.utc).year}'
            })
            denied = await client.post(f'{API}/alquileres/{second.json()["id"]}/pagar')
            assert denied.status_code == 409
            after = await db.contadores.find_one({"_id": before["_id"]})
            assert after["seq"] == before["seq"]
            still_processing = await db.alquileres.find_one({"id": second.json()["id"]})
            assert still_processing["estado"] == "procesando"

    mongo_rental_api["loop"].run_until_complete(run())


def test_payment_failure_keeps_reservation_and_does_not_reuse_receipt_number(mongo_rental_api, monkeypatch):
    async def run():
        db = mongo_rental_api["db"]
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            booking = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"],
                ),
            )
            assert booking.status_code == 201
            original_finalize = server._finalize_rental_payment
            injected = {"enabled": True}

            async def fail_paid_transition(rental_id, payment_token, update):
                if injected["enabled"]:
                    injected["enabled"] = False
                    raise RuntimeError("injected final update failure")
                return await original_finalize(rental_id, payment_token, update)

            monkeypatch.setattr(server, "_finalize_rental_payment", fail_paid_transition)
            failed = await client.post(f'{API}/alquileres/{booking.json()["id"]}/pagar')
            assert failed.status_code == 500
            assert booking.json()["id"] in failed.json()["detail"]
            preserved = await db.alquileres.find_one({"id": booking.json()["id"]})
            assert preserved["estado"] == "reservado"
            assert preserved.get("cod_comprobante") is None
            counter_id = f'comprobante_{mongo_rental_api["office_a"]}_{datetime.now(timezone.utc).year}'
            assert (await db.contadores.find_one({"_id": counter_id}))["seq"] == 1

            retried = await client.post(f'{API}/alquileres/{booking.json()["id"]}/pagar')
            assert retried.status_code == 200, retried.text
            assert retried.json()["cod_comprobante"] == "00002"

    mongo_rental_api["loop"].run_until_complete(run())


def test_concurrent_rental_and_deleted_pago_draft_keep_shared_counter_append_only(mongo_rental_api, monkeypatch):
    async def run():
        db = mongo_rental_api["db"]
        year = datetime.now(timezone.utc).year
        await db.estudiantes.insert_one({
            "id": "counter-student-a", "office_id": mongo_rental_api["office_a"],
            "ci": "COUNTER-CI", "cu": "COUNTER-CU", "nombre": "Counter Test",
            "gestion": year,
        })
        await db.tipos_pagos.insert_one({
            "id": "counter-type-a", "office_id": mongo_rental_api["office_a"],
            "nombre": "Counter concept", "nombre_key": "counter concept",
            "monto": 5.0, "descripcion": "", "inicio": f"{year}-01-01",
        })
        async with await _client(_actor()) as client:
            tariff = await client.post(
                f"{API}/tarifas-ambientes",
                json=_tariff_payload(mongo_rental_api["ambiente_a"]),
            )
            booking = await client.post(
                f"{API}/alquileres",
                json=_rental_payload(
                    mongo_rental_api["ambiente_a"], tariff.json()["id"],
                    mongo_rental_api["monday"], cobrar_ahora=False,
                ),
            )
            assert booking.status_code == 201
            allocated = asyncio.Event()
            finish_payment = asyncio.Event()
            original_finalize = server._finalize_rental_payment

            async def pause_before_final_update(rental_id, payment_token, update):
                allocated.set()
                await finish_payment.wait()
                return await original_finalize(rental_id, payment_token, update)

            monkeypatch.setattr(server, "_finalize_rental_payment", pause_before_final_update)
            rental_payment_task = asyncio.create_task(
                client.post(f'{API}/alquileres/{booking.json()["id"]}/pagar')
            )
            await asyncio.wait_for(allocated.wait(), timeout=5)

            draft = await client.post(
                f"{API}/pagos",
                json={
                    "id_estudiante": "counter-student-a",
                    "fecha_pago": date.today().isoformat(),
                    "office_id": mongo_rental_api["office_a"],
                },
            )
            assert draft.status_code == 201, draft.text
            draft_code = draft.json()["cod_comprobante"]
            deleted = await client.delete(f'{API}/pagos/{draft.json()["id"]}/borrador')
            assert deleted.status_code == 200
            assert deleted.json()["correlativo_reutilizado"] is False

            finish_payment.set()
            paid_rental_response = await rental_payment_task
            assert paid_rental_response.status_code == 200, paid_rental_response.text
            rental_code = paid_rental_response.json()["cod_comprobante"]
            assert int(draft_code) > int(rental_code)

            next_pago = await client.post(
                f"{API}/pagos",
                json={
                    "id_estudiante": "counter-student-a",
                    "fecha_pago": date.today().isoformat(),
                    "office_id": mongo_rental_api["office_a"],
                    "id_tipo_pago": "counter-type-a",
                    "cantidad": 1,
                },
            )
            assert next_pago.status_code == 201, next_pago.text
            assert int(next_pago.json()["cod_comprobante"]) > int(draft_code)
            rental_receipts = await db.alquileres.find(
                {"estado": "pagado"}, {"_id": 0, "cod_comprobante": 1}
            ).to_list(None)
            pago_receipts = await db.pagos.find(
                {"estado": "emitido"}, {"_id": 0, "cod_comprobante": 1}
            ).to_list(None)
            all_codes = [row["cod_comprobante"] for row in rental_receipts + pago_receipts]
            assert len(all_codes) == len(set(all_codes))
            counter = await db.contadores.find_one({
                "_id": f'comprobante_{mongo_rental_api["office_a"]}_{year}'
            })
            assert counter["seq"] == int(next_pago.json()["cod_comprobante"])

    mongo_rental_api["loop"].run_until_complete(run())


def test_alquiler_list_and_schedule_validation_cover_more_than_1000_records(mongo_rental_api):
    async def run():
        db = mongo_rental_api["db"]
        fecha = mongo_rental_api["monday"]
        rentals = []
        for index in range(1000):
            rentals.append({
                "id": f"bulk-valid-{index:04d}",
                "office_id": mongo_rental_api["office_a"],
                "ambiente_id": mongo_rental_api["ambiente_a"],
                "ambiente_nombre": "Bulk room",
                "fecha": fecha,
                "tramos": [{"desde": "09:00", "hasta": "10:00"}],
                "estado": "reservado",
                "created_at": f"2026-01-01T00:{index % 60:02d}:00+00:00",
            })
        rentals.append({
            "id": "bulk-last-invalid-for-new-schedule",
            "office_id": mongo_rental_api["office_a"],
            "ambiente_id": mongo_rental_api["ambiente_a"],
            "ambiente_nombre": "Bulk room",
            "fecha": fecha,
            "tramos": [{"desde": "10:00", "hasta": "11:00"}],
            "estado": "reservado",
            "created_at": "2026-12-31T23:59:00+00:00",
        })
        await db.alquileres.insert_many(rentals)
        async with await _client(_actor()) as client:
            response = await client.get(
                f"{API}/alquileres",
                params={
                    "ambiente_id": mongo_rental_api["ambiente_a"],
                    "fecha_desde": fecha,
                    "fecha_hasta": fecha,
                },
            )
            assert response.status_code == 200
            assert len(response.json()) == 1001

            update = await client.put(
                f'{API}/ambientes/{mongo_rental_api["ambiente_a"]}',
                json={
                    "nombre": "Room office-a",
                    "horarios": [{"dia": "lunes", "desde": "09:00", "hasta": "10:00"}],
                },
            )
            assert update.status_code == 400
            unchanged = await db.ambientes.find_one({"id": mongo_rental_api["ambiente_a"]})
            assert unchanged["horarios"][0]["hasta"] == "12:00"

    mongo_rental_api["loop"].run_until_complete(run())


def test_startup_receipt_reconciliation_never_decreases_counter(mongo_rental_api):
    async def run():
        db = mongo_rental_api["db"]
        year = datetime.now(timezone.utc).year
        counter_id = f'comprobante_{mongo_rental_api["office_a"]}_{year}'
        await db.contadores.insert_one({"_id": counter_id, "seq": 50})
        await db.alquileres.insert_one({
            "id": "paid-receipt-existing", "office_id": mongo_rental_api["office_a"],
            "gestion": year, "cod_comprobante": "00004", "estado": "pagado",
        })
        await server.reconcile_payment_counters()
        counter = await db.contadores.find_one({"_id": counter_id})
        assert counter["seq"] == 50

    mongo_rental_api["loop"].run_until_complete(run())
