"""Inspección estática del contrato de reportes; no importa ni conecta SQL Server."""
import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
SOURCE = (BACKEND / "serverSQL2012.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
SCHEMA = (BACKEND / "Tablas.Sql").read_text(encoding="utf-8")


def _function(name):
    return next(
        node for node in TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def test_report_endpoint_batches_hydration_instead_of_querying_per_receipt():
    report_source = ast.get_source_segment(SOURCE, _function("reports"))
    calls = {
        node.func.id
        for node in ast.walk(_function("reports"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "_hydrate_report_payments" in calls
    assert "_hydrate_report_rentals" in calls
    assert "hydrate_payment" not in calls
    assert "hydrate_rental" not in calls
    assert "LEFT JOIN clientes" in report_source
    assert "LEFT JOIN ambientes" in report_source
    assert "LEFT JOIN tarifas_ambientes" in report_source
    assert "asyncio.gather" in report_source


def test_report_date_filters_bind_native_date_values():
    report = _function("reports")
    assignments = {
        target.id: node.value
        for node in report.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    for name in ("pv", "ra"):
        assert isinstance(assignments[name], ast.List)
        assert [item.id for item in assignments[name].elts] == ["start", "end"]


def test_report_batch_queries_stay_below_sql_server_parameter_limit():
    batch_source = ast.get_source_segment(SOURCE, _function("_report_rows_for_ids"))
    assert "range(0, len(identifiers), 800)" in batch_source
    assert "IN ({placeholders})" in SOURCE


def test_schema_has_indexes_for_report_filters_and_batched_details():
    assert "ON dbo.pagos(id_oficina,fecha_pago)" in SCHEMA
    assert "INCLUDE(estado,created_by,anulado,total,id_cliente," in SCHEMA
    assert "ON dbo.pago_items(id_pago,id)" in SCHEMA
    assert "ON dbo.alquileres(id_oficina,fecha_pago)" in SCHEMA
    assert "INCLUDE(estado,registrado_por,cod_comprobante" in SCHEMA
    assert "total,id_cliente,\n          nombre_cliente,id_ambiente,id_tarifa,cantidad,monto" in SCHEMA
    assert "ON dbo.alquiler_intervalos(alquiler_id,desde) INCLUDE(hasta)" in SCHEMA
    assert "paid_by" not in SCHEMA
    assert "cliente_id" not in SCHEMA
    assert "cliente_nombre" not in SCHEMA
    assert "ambiente_id" not in SCHEMA
    assert "tarifa_id" not in SCHEMA
    assert "pago_id" not in SCHEMA
