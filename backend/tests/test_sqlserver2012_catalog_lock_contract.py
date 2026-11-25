"""Inspección estática del bloqueo de catálogos; no ejecuta SQL Server."""
import ast
from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "serverSQL2012.py").read_text(
    encoding="utf-8"
)
TREE = ast.parse(SOURCE)


def _function(name):
    return next(
        node for node in TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def test_concepts_with_payments_are_marked_and_cannot_be_updated():
    listing = ast.get_source_segment(SOURCE, _function("concepts"))
    update = ast.get_source_segment(SOURCE, _function("update_concept"))

    assert "AS bloqueado" in listing
    assert "FROM pago_items i" in listing
    assert "No se puede editar: el concepto tiene pagos registrados." in update
    assert "SELECT TOP 1 p.id FROM pagos p" in update
    assert "FROM pago_items i" in update


def test_tariffs_with_rentals_are_marked_and_cannot_be_updated():
    listing = ast.get_source_segment(SOURCE, _function("tariffs"))
    update = ast.get_source_segment(SOURCE, _function("update_tariff"))

    assert "AS bloqueado" in listing
    assert "FROM alquileres a WHERE a.tarifa_id=t.id" in listing
    assert "No se puede editar: la tarifa tiene alquileres registrados." in update
    assert "SELECT TOP 1 id FROM alquileres WHERE tarifa_id=?" in update
