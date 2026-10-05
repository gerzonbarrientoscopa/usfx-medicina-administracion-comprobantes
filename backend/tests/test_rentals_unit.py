"""Focused, database-independent validation tests for room rentals."""
import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "rental_unit_tests")
os.environ.setdefault("JWT_SECRET", "unit-test-secret")
os.environ.setdefault("ADMIN_PASSWORD", "unit-test-password")
os.environ.setdefault("ADMIN_NAME", "Unit Test Admin")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from pydantic import ValidationError

from server import (
    AmbienteCreate,
    AlquilerCreate,
    TarifaAmbienteCreate,
    _covered_by_schedule,
    _intervals_overlap,
    _minute_of_day,
)


def test_tariff_fixed_modalities_require_strict_ordered_times():
    valid = TarifaAmbienteCreate(
        ambiente_id="room-1",
        nombre="Mañana",
        modalidad="manana",
        monto="25.00",
        desde="08:00",
        hasta="12:00",
    )
    assert valid.monto == 25

    with pytest.raises(ValidationError):
        TarifaAmbienteCreate(
            ambiente_id="room-1", nombre="Mañana", modalidad="manana",
            monto="25", desde="8:00", hasta="12:00",
        )
    with pytest.raises(ValidationError):
        TarifaAmbienteCreate(
            ambiente_id="room-1", nombre="Mañana", modalidad="manana",
            monto="25", desde="12:00", hasta="12:00",
        )


def test_night_tariff_and_three_room_shifts_are_validated():
    night = TarifaAmbienteCreate(
        ambiente_id="room-1", nombre="Noche", modalidad="noche",
        monto="45.00", desde="18:00", hasta="22:00",
    )
    assert night.modalidad == "noche"

    room = AmbienteCreate(
        nombre="Sala",
        turnos=[
            {"turno": "manana", "desde": "08:00", "hasta": "12:00"},
            {"turno": "tarde", "desde": "13:00", "hasta": "17:00"},
            {"turno": "noche", "desde": "18:00", "hasta": "22:00"},
        ],
    )
    assert [turno.turno for turno in room.turnos] == ["manana", "tarde", "noche"]

    with pytest.raises(ValidationError):
        AmbienteCreate(
            nombre="Turnos superpuestos",
            turnos=[
                {"turno": "manana", "desde": "08:00", "hasta": "12:00"},
                {"turno": "tarde", "desde": "11:00", "hasta": "17:00"},
                {"turno": "noche", "desde": "18:00", "hasta": "22:00"},
            ],
        )


def test_tariff_nonfixed_modes_reject_times_and_currency_precision():
    with pytest.raises(ValidationError):
        TarifaAmbienteCreate(
            ambiente_id="room-1", nombre="Por hora", modalidad="hora",
            monto="10", desde="08:00",
        )
    with pytest.raises(ValidationError):
        TarifaAmbienteCreate(
            ambiente_id="room-1", nombre="Por hora", modalidad="hora",
            monto="0",
        )
    with pytest.raises(ValidationError):
        TarifaAmbienteCreate(
            ambiente_id="room-1", nombre="Por hora", modalidad="hora",
            monto="10.001",
        )


def test_schedule_coverage_requires_full_contiguous_open_interval():
    schedule = [("08:00", "12:00"), ("13:00", "17:00")]
    assert _covered_by_schedule(schedule, "09:00", "11:00")
    assert not _covered_by_schedule(schedule, "11:30", "13:30")
    assert _covered_by_schedule([("08:00", "10:00"), ("10:00", "12:00")], "09:30", "10:30")
    assert _minute_of_day("01:30") == 90


def test_reservations_overlap_but_adjacent_intervals_do_not():
    assert _intervals_overlap(9 * 60, 10 * 60, 9 * 60 + 30, 11 * 60)
    assert not _intervals_overlap(9 * 60, 10 * 60, 10 * 60, 11 * 60)


@pytest.mark.parametrize("client_type", ["persona", "estudiante"])
def test_rental_accepts_both_payer_catalogs(client_type):
    rental = AlquilerCreate(
        ambiente_id="room-1",
        tarifa_id="tariff-1",
        fecha="2026-04-20",
        desde="09:00",
        hasta="10:00",
        cliente_tipo=client_type,
        cliente_id="client-1",
        cobrar_ahora=False,
    )
    assert rental.cliente_tipo == client_type