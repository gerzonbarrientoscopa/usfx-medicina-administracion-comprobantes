"""Backend API tests for Comprobantes USFX - Aplicación contable universitaria"""
import os
import uuid
from datetime import date

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://edu-payment-portal-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@usfx.edu.bo"
ADMIN_PASSWORD = "admin123"

CAJA_EMAIL = f"TEST_caja_{uuid.uuid4().hex[:6]}@usfx.edu.bo"
CAJA_PASSWORD = "caja1234"
CONS_EMAIL = f"TEST_cons_{uuid.uuid4().hex[:6]}@usfx.edu.bo"
CONS_PASSWORD = "cons1234"


# -------- Fixtures --------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and data["user"]["role"] == "admin"
    return data["token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def caja_token(admin_token):
    # Create caja user via admin
    payload = {"email": CAJA_EMAIL, "name": "Test Caja", "password": CAJA_PASSWORD, "role": "caja"}
    r = requests.post(f"{API}/users", json=payload, headers=auth_headers(admin_token))
    assert r.status_code in (201, 400), f"create caja: {r.status_code} {r.text}"
    r = requests.post(f"{API}/auth/login", json={"email": CAJA_EMAIL, "password": CAJA_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def consultas_token(admin_token):
    payload = {"email": CONS_EMAIL, "name": "Test Consultas", "password": CONS_PASSWORD, "role": "consultas"}
    r = requests.post(f"{API}/users", json=payload, headers=auth_headers(admin_token))
    assert r.status_code in (201, 400), r.text
    r = requests.post(f"{API}/auth/login", json={"email": CONS_EMAIL, "password": CONS_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# -------- Auth tests --------
class TestAuth:
    def test_login_admin(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_me(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers=auth_headers(admin_token))
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL
        assert r.json()["role"] == "admin"

    def test_invalid_login(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_me_no_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_logout(self, admin_token):
        r = requests.post(f"{API}/auth/logout", headers=auth_headers(admin_token))
        assert r.status_code == 200


# -------- Users tests --------
class TestUsers:
    def test_create_user_requires_admin(self, caja_token):
        r = requests.post(f"{API}/users", json={"email": "x@x.com", "name": "x", "password": "1234", "role": "caja"},
                          headers=auth_headers(caja_token))
        assert r.status_code == 403

    def test_list_users_admin(self, admin_token):
        r = requests.get(f"{API}/users", headers=auth_headers(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_users_forbidden(self, consultas_token):
        r = requests.get(f"{API}/users", headers=auth_headers(consultas_token))
        assert r.status_code == 403

    def test_caja_login_works(self, caja_token):
        r = requests.get(f"{API}/auth/me", headers=auth_headers(caja_token))
        assert r.status_code == 200
        assert r.json()["role"] == "caja"

    def test_consultas_login_works(self, consultas_token):
        r = requests.get(f"{API}/auth/me", headers=auth_headers(consultas_token))
        assert r.status_code == 200
        assert r.json()["role"] == "consultas"


# -------- Estudiantes tests --------
@pytest.fixture(scope="session")
def estudiante_id(admin_token):
    codigo = f"TEST{uuid.uuid4().hex[:6].upper()}"
    payload = {"codigo": codigo, "ci": "1234567", "cu": "CU001", "nombre": "TEST Juan Perez", "gestion": 2026}
    r = requests.post(f"{API}/estudiantes", json=payload, headers=auth_headers(admin_token))
    assert r.status_code == 201, r.text
    return r.json()["id"], codigo


class TestEstudiantes:
    def test_create_and_get(self, admin_token, estudiante_id):
        eid, codigo = estudiante_id
        r = requests.get(f"{API}/estudiantes?q={codigo}", headers=auth_headers(admin_token))
        assert r.status_code == 200
        assert any(e["id"] == eid for e in r.json())

    def test_duplicate_codigo(self, admin_token, estudiante_id):
        _, codigo = estudiante_id
        r = requests.post(f"{API}/estudiantes",
                          json={"codigo": codigo, "ci": "9", "cu": "", "nombre": "dup", "gestion": 2026},
                          headers=auth_headers(admin_token))
        assert r.status_code == 400

    def test_update_estudiante(self, admin_token, estudiante_id):
        eid, codigo = estudiante_id
        r = requests.put(f"{API}/estudiantes/{eid}",
                         json={"codigo": codigo, "ci": "1234567", "cu": "CU001", "nombre": "TEST Juan Actualizado",
                               "gestion": 2026},
                         headers=auth_headers(admin_token))
        assert r.status_code == 200
        assert r.json()["nombre"] == "TEST Juan Actualizado"

    def test_caja_cannot_update_estudiante(self, caja_token, estudiante_id):
        eid, codigo = estudiante_id
        r = requests.put(f"{API}/estudiantes/{eid}",
                         json={"codigo": codigo, "ci": "1", "cu": "", "nombre": "x", "gestion": 2026},
                         headers=auth_headers(caja_token))
        assert r.status_code == 403

    def test_caja_can_create_estudiante(self, caja_token):
        codigo = f"TEST{uuid.uuid4().hex[:6].upper()}"
        r = requests.post(f"{API}/estudiantes",
                          json={"codigo": codigo, "ci": "9999", "cu": "", "nombre": "TEST Caja Creado",
                                "gestion": 2026},
                          headers=auth_headers(caja_token))
        assert r.status_code == 201

    def test_consultas_cannot_create(self, consultas_token):
        r = requests.post(f"{API}/estudiantes",
                          json={"codigo": "X", "ci": "1", "cu": "", "nombre": "x", "gestion": 2026},
                          headers=auth_headers(consultas_token))
        assert r.status_code == 403

    def test_consultas_can_list(self, consultas_token):
        r = requests.get(f"{API}/estudiantes", headers=auth_headers(consultas_token))
        assert r.status_code == 200


# -------- TiposPagos tests --------
@pytest.fixture(scope="session")
def tipopago_id(admin_token):
    codigo = f"TP{uuid.uuid4().hex[:6].upper()}"
    payload = {"codigo": codigo, "nombre": "TEST Matricula", "monto": 250.0, "descripcion": "test",
               "inicio": "2026-01-01", "fin": "2026-12-31"}
    r = requests.post(f"{API}/tipospagos", json=payload, headers=auth_headers(admin_token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestTiposPagos:
    def test_create_and_list(self, admin_token, tipopago_id):
        r = requests.get(f"{API}/tipospagos", headers=auth_headers(admin_token))
        assert r.status_code == 200
        assert any(t["id"] == tipopago_id for t in r.json())

    def test_caja_cannot_create_tipopago(self, caja_token):
        r = requests.post(f"{API}/tipospagos",
                          json={"codigo": "X", "nombre": "x", "monto": 1, "descripcion": "", "inicio": "2026-01-01"},
                          headers=auth_headers(caja_token))
        assert r.status_code == 403

    def test_update_tipopago(self, admin_token, tipopago_id):
        r = requests.put(f"{API}/tipospagos/{tipopago_id}",
                         json={"codigo": f"TPU{uuid.uuid4().hex[:5]}", "nombre": "TEST Matricula Updated",
                               "monto": 300.0, "descripcion": "", "inicio": "2026-01-01", "fin": "2026-12-31"},
                         headers=auth_headers(admin_token))
        assert r.status_code == 200
        assert r.json()["monto"] == 300.0


# -------- Pagos tests --------
class TestPagos:
    def test_preview_comprobante(self, caja_token):
        r = requests.get(f"{API}/pagos/preview-comprobante", headers=auth_headers(caja_token))
        assert r.status_code == 200
        data = r.json()
        assert "codcomprobante" in data and "gestion" in data and "display" in data
        assert len(data["codcomprobante"]) == 5
        assert "/" in data["display"]

    def test_create_pago_and_correlativo(self, caja_token, estudiante_id, tipopago_id):
        eid, _ = estudiante_id
        # preview
        r0 = requests.get(f"{API}/pagos/preview-comprobante", headers=auth_headers(caja_token))
        before = int(r0.json()["codcomprobante"])
        # create
        payload = {"id_estudiante": eid, "id_tipopago": tipopago_id, "cantidad": 2, "fecha_pago": date.today().isoformat()}
        r = requests.post(f"{API}/pagos", json=payload, headers=auth_headers(caja_token))
        assert r.status_code == 201, r.text
        p1 = r.json()
        assert p1["total"] == p1["monto"] * 2
        assert int(p1["codcomprobante"]) == before
        # create another - correlativo should increment
        r2 = requests.post(f"{API}/pagos", json=payload, headers=auth_headers(caja_token))
        assert r2.status_code == 201
        p2 = r2.json()
        assert int(p2["codcomprobante"]) == int(p1["codcomprobante"]) + 1
        # save pago id for anular
        pytest.last_pago_id = p1["id"]
        pytest.second_pago_id = p2["id"]

    def test_list_pagos_filter(self, admin_token, tipopago_id):
        r = requests.get(f"{API}/pagos?id_tipopago={tipopago_id}", headers=auth_headers(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_consultas_can_list_pagos(self, consultas_token):
        r = requests.get(f"{API}/pagos", headers=auth_headers(consultas_token))
        assert r.status_code == 200

    def test_caja_cannot_anular(self, caja_token):
        pid = getattr(pytest, "last_pago_id", None)
        if not pid:
            pytest.skip("no pago created")
        r = requests.post(f"{API}/pagos/{pid}/anular", headers=auth_headers(caja_token))
        assert r.status_code == 403

    def test_admin_anular_pago(self, admin_token):
        pid = getattr(pytest, "last_pago_id", None)
        if not pid:
            pytest.skip("no pago created")
        r = requests.post(f"{API}/pagos/{pid}/anular", headers=auth_headers(admin_token))
        assert r.status_code == 200
        # verify in list with incluir_anulados
        r2 = requests.get(f"{API}/pagos?incluir_anulados=true", headers=auth_headers(admin_token))
        anulado = next((p for p in r2.json() if p["id"] == pid), None)
        assert anulado and anulado["anulado"] is True and anulado["anulado_at"]

    def test_double_anular_rejected(self, admin_token):
        pid = getattr(pytest, "last_pago_id", None)
        if not pid:
            pytest.skip("no pago created")
        r = requests.post(f"{API}/pagos/{pid}/anular", headers=auth_headers(admin_token))
        assert r.status_code == 400


# -------- Reportes tests --------
class TestReportes:
    def test_reportes_diario_admin(self, admin_token):
        r = requests.get(f"{API}/reportes?periodo=diario", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "pagos" in data and "totales" in data
        t = data["totales"]
        for k in ("validos", "anulados", "diferencia", "count_validos", "count_anulados"):
            assert k in t
        assert abs(t["diferencia"] - (t["validos"] - t["anulados"])) < 0.001

    def test_reportes_semanal(self, admin_token):
        r = requests.get(f"{API}/reportes?periodo=semanal", headers=auth_headers(admin_token))
        assert r.status_code == 200

    def test_reportes_mensual(self, admin_token):
        r = requests.get(f"{API}/reportes?periodo=mensual", headers=auth_headers(admin_token))
        assert r.status_code == 200

    def test_reportes_rango(self, admin_token):
        r = requests.get(f"{API}/reportes?periodo=rango&desde=2026-01-01&hasta=2026-12-31",
                         headers=auth_headers(admin_token))
        assert r.status_code == 200

    def test_reportes_rango_missing(self, admin_token):
        r = requests.get(f"{API}/reportes?periodo=rango", headers=auth_headers(admin_token))
        assert r.status_code == 400

    def test_caja_cannot_view_reportes(self, caja_token):
        r = requests.get(f"{API}/reportes?periodo=diario", headers=auth_headers(caja_token))
        assert r.status_code == 403


# -------- Dashboard stats --------
class TestDashboard:
    def test_stats(self, admin_token):
        r = requests.get(f"{API}/dashboard/stats", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        for k in ("estudiantes", "tipospagos", "pagos_hoy", "monto_hoy"):
            assert k in data

    def test_stats_caja(self, caja_token):
        r = requests.get(f"{API}/dashboard/stats", headers=auth_headers(caja_token))
        assert r.status_code == 200



# -------- Iteration 2: new features --------
class TestUsersList:
    """GET /api/users/list — minimal listing for filters; all roles allowed."""

    def test_admin_can_list(self, admin_token):
        r = requests.get(f"{API}/users/list", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 1
        for u in data:
            assert set(u.keys()) >= {"id", "name", "role"}
        # sorted by name asc
        names = [u["name"] for u in data]
        assert names == sorted(names, key=lambda s: s.lower()) or names == sorted(names)

    def test_caja_can_list(self, caja_token):
        r = requests.get(f"{API}/users/list", headers=auth_headers(caja_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_consultas_can_list(self, consultas_token):
        r = requests.get(f"{API}/users/list", headers=auth_headers(consultas_token))
        assert r.status_code == 200

    def test_unauthenticated_blocked(self):
        r = requests.get(f"{API}/users/list")
        assert r.status_code == 401


class TestPagoEditAndCreatedByFilter:
    """PUT /api/pagos/{id} edit; created_by filter; hydrated names."""

    def _create_pago(self, token, estudiante_id, tipopago_id, cantidad=3):
        eid, _ = estudiante_id
        payload = {"id_estudiante": eid, "id_tipopago": tipopago_id, "cantidad": cantidad,
                   "fecha_pago": date.today().isoformat()}
        r = requests.post(f"{API}/pagos", json=payload, headers=auth_headers(token))
        assert r.status_code == 201, r.text
        return r.json()

    def test_created_by_name_hydrated(self, caja_token, admin_token, estudiante_id, tipopago_id):
        p = self._create_pago(caja_token, estudiante_id, tipopago_id, 1)
        # fetch via list
        r = requests.get(f"{API}/pagos", headers=auth_headers(admin_token))
        assert r.status_code == 200
        found = next((x for x in r.json() if x["id"] == p["id"]), None)
        assert found is not None
        assert found.get("created_by_name") == "Test Caja"
        pytest.edit_pago_id = p["id"]
        pytest.edit_pago_monto = p["monto"]

    def test_admin_edit_pago_updates_total(self, admin_token, tipopago_id):
        pid = getattr(pytest, "edit_pago_id", None)
        monto = getattr(pytest, "edit_pago_monto", None)
        assert pid and monto
        r = requests.put(f"{API}/pagos/{pid}", json={"cantidad": 5},
                         headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["cantidad"] == 5
        assert abs(data["total"] - monto * 5) < 0.001
        assert data.get("edited_at")
        assert data.get("edited_by")
        assert data.get("edited_by_name")  # admin name

        # Verify via GET
        r2 = requests.get(f"{API}/pagos", headers=auth_headers(admin_token))
        found = next((x for x in r2.json() if x["id"] == pid), None)
        assert found and found["cantidad"] == 5 and abs(found["total"] - monto * 5) < 0.001

    def test_edit_change_tipopago_recalculates(self, admin_token, estudiante_id, caja_token):
        # create new tp with different monto
        codigo = f"TP2{uuid.uuid4().hex[:5].upper()}"
        r_tp = requests.post(f"{API}/tipospagos",
                             json={"codigo": codigo, "nombre": "TEST TP Edit", "monto": 100.0,
                                   "descripcion": "", "inicio": "2026-01-01", "fin": "2026-12-31"},
                             headers=auth_headers(admin_token))
        assert r_tp.status_code == 201
        new_tp_id = r_tp.json()["id"]
        # create a pago and then edit to switch tp
        codigo2 = f"TP3{uuid.uuid4().hex[:5].upper()}"
        r_tp2 = requests.post(f"{API}/tipospagos",
                              json={"codigo": codigo2, "nombre": "TEST TP Orig", "monto": 50.0,
                                    "descripcion": "", "inicio": "2026-01-01", "fin": "2026-12-31"},
                              headers=auth_headers(admin_token))
        assert r_tp2.status_code == 201
        orig_tp_id = r_tp2.json()["id"]
        eid, _ = estudiante_id
        rp = requests.post(f"{API}/pagos",
                           json={"id_estudiante": eid, "id_tipopago": orig_tp_id, "cantidad": 2,
                                 "fecha_pago": date.today().isoformat()},
                           headers=auth_headers(caja_token))
        assert rp.status_code == 201
        pid = rp.json()["id"]
        # edit -> change tipopago, expect monto and total recompute
        ru = requests.put(f"{API}/pagos/{pid}", json={"id_tipopago": new_tp_id},
                          headers=auth_headers(admin_token))
        assert ru.status_code == 200, ru.text
        d = ru.json()
        assert d["id_tipopago"] == new_tp_id
        assert d["monto"] == 100.0
        assert d["total"] == 100.0 * 2

    def test_caja_cannot_edit(self, caja_token, estudiante_id, tipopago_id):
        p = self._create_pago(caja_token, estudiante_id, tipopago_id, 1)
        r = requests.put(f"{API}/pagos/{p['id']}", json={"cantidad": 9},
                         headers=auth_headers(caja_token))
        assert r.status_code == 403

    def test_consultas_cannot_edit(self, consultas_token, admin_token, estudiante_id, tipopago_id, caja_token):
        p = self._create_pago(caja_token, estudiante_id, tipopago_id, 1)
        r = requests.put(f"{API}/pagos/{p['id']}", json={"cantidad": 9},
                         headers=auth_headers(consultas_token))
        assert r.status_code == 403

    def test_cannot_edit_anulado(self, admin_token, caja_token, estudiante_id, tipopago_id):
        p = self._create_pago(caja_token, estudiante_id, tipopago_id, 1)
        # anular
        ra = requests.post(f"{API}/pagos/{p['id']}/anular", headers=auth_headers(admin_token))
        assert ra.status_code == 200
        # try to edit
        r = requests.put(f"{API}/pagos/{p['id']}", json={"cantidad": 9},
                         headers=auth_headers(admin_token))
        assert r.status_code == 400

    def test_edit_no_changes_rejected(self, admin_token, caja_token, estudiante_id, tipopago_id):
        p = self._create_pago(caja_token, estudiante_id, tipopago_id, 2)
        r = requests.put(f"{API}/pagos/{p['id']}", json={"cantidad": 2},
                         headers=auth_headers(admin_token))
        assert r.status_code == 400

    def test_edit_invalid_estudiante(self, admin_token, caja_token, estudiante_id, tipopago_id):
        p = self._create_pago(caja_token, estudiante_id, tipopago_id, 1)
        r = requests.put(f"{API}/pagos/{p['id']}",
                         json={"id_estudiante": "00000000-0000-0000-0000-000000000000"},
                         headers=auth_headers(admin_token))
        assert r.status_code == 400

    def test_created_by_filter_on_pagos(self, admin_token, caja_token):
        # get caja user id
        ru = requests.get(f"{API}/users/list", headers=auth_headers(admin_token))
        caja_user = next((u for u in ru.json() if u["role"] == "caja" and u["name"] == "Test Caja"), None)
        assert caja_user is not None
        r = requests.get(f"{API}/pagos?created_by={caja_user['id']}",
                         headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # All returned pagos must have created_by == caja_user.id
        for p in data:
            assert p.get("created_by") == caja_user["id"]
        # And every test pago we created should be admin-or-caja owned; at least one with this filter
        assert len(data) >= 1

    def test_created_by_filter_on_reportes(self, admin_token):
        ru = requests.get(f"{API}/users/list", headers=auth_headers(admin_token))
        caja_user = next((u for u in ru.json() if u["role"] == "caja" and u["name"] == "Test Caja"), None)
        assert caja_user
        r = requests.get(
            f"{API}/reportes?periodo=rango&desde=2026-01-01&hasta=2026-12-31&created_by={caja_user['id']}",
            headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        for p in data["pagos"]:
            assert p.get("created_by") == caja_user["id"]

    def test_edit_pago_not_found(self, admin_token):
        r = requests.put(f"{API}/pagos/non-existent-id", json={"cantidad": 5},
                         headers=auth_headers(admin_token))
        assert r.status_code == 404


# -------- Iteration 3 (P2 refactor): /api/pagos and /api/reportes via $lookup aggregation --------
class TestAggregationRefactor:
    """Verify the $lookup aggregation pipeline preserves the existing API contract:
    same hydrated shape, same filters, same sorting."""

    def test_pagos_shape_includes_hydrated_fields(self, admin_token, caja_token, estudiante_id, tipopago_id):
        # Create a fresh pago so we know at least one exists
        eid, _ = estudiante_id
        payload = {"id_estudiante": eid, "id_tipopago": tipopago_id, "cantidad": 1,
                   "fecha_pago": date.today().isoformat()}
        rc = requests.post(f"{API}/pagos", json=payload, headers=auth_headers(caja_token))
        assert rc.status_code == 201
        pid = rc.json()["id"]

        r = requests.get(f"{API}/pagos", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 1
        found = next((p for p in data if p["id"] == pid), None)
        assert found is not None, "newly created pago missing from list"
        # Hydrated fields produced by aggregation $lookup
        for k in ("estudiante_nombre", "estudiante_ci", "estudiante_cu",
                  "tipopago_nombre", "created_by_name"):
            assert k in found, f"hydrated field {k} missing from /api/pagos response"
        assert found["created_by_name"] == "Test Caja"
        # edited_by_name should be present (None) or absent before any edit
        # but the schema PagoOut should expose it
        assert "edited_by_name" in found

    def test_pagos_sorted_by_created_at_desc(self, admin_token, caja_token, estudiante_id, tipopago_id):
        # Create two pagos and verify the newer one appears first
        eid, _ = estudiante_id
        payload = {"id_estudiante": eid, "id_tipopago": tipopago_id, "cantidad": 1,
                   "fecha_pago": date.today().isoformat()}
        r1 = requests.post(f"{API}/pagos", json=payload, headers=auth_headers(caja_token))
        assert r1.status_code == 201
        r2 = requests.post(f"{API}/pagos", json=payload, headers=auth_headers(caja_token))
        assert r2.status_code == 201
        p1_id, p2_id = r1.json()["id"], r2.json()["id"]

        r = requests.get(f"{API}/pagos", headers=auth_headers(admin_token))
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()]
        assert p2_id in ids and p1_id in ids
        # p2 (created last) must come before p1
        assert ids.index(p2_id) < ids.index(p1_id), "pagos not sorted DESC by created_at"

        # Also assert created_at strings are monotonically non-increasing
        cas = [p.get("created_at") for p in r.json() if p.get("created_at")]
        assert cas == sorted(cas, reverse=True), "created_at not sorted DESC"

    def test_pagos_q_by_codcomprobante_gestion(self, admin_token, caja_token, estudiante_id, tipopago_id):
        # create pago and search by "cod/gestion"
        eid, _ = estudiante_id
        payload = {"id_estudiante": eid, "id_tipopago": tipopago_id, "cantidad": 1,
                   "fecha_pago": date.today().isoformat()}
        rc = requests.post(f"{API}/pagos", json=payload, headers=auth_headers(caja_token))
        assert rc.status_code == 201
        p = rc.json()
        q = f"{p['codcomprobante']}/{p['gestion']}"
        r = requests.get(f"{API}/pagos?q={q}", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert any(x["id"] == p["id"] for x in data), f"q={q} did not return pago {p['id']}"

    def test_pagos_q_by_estudiante_name(self, admin_token, caja_token, estudiante_id, tipopago_id):
        # estudiante_id fixture returns (id, codigo) and seeds estudiante with nombre "TEST Juan ..."
        eid, _ = estudiante_id
        payload = {"id_estudiante": eid, "id_tipopago": tipopago_id, "cantidad": 1,
                   "fecha_pago": date.today().isoformat()}
        rc = requests.post(f"{API}/pagos", json=payload, headers=auth_headers(caja_token))
        assert rc.status_code == 201
        pid = rc.json()["id"]
        # Search by a substring of the estudiante name ("Juan" is in TEST Juan Perez / Actualizado)
        r = requests.get(f"{API}/pagos?q=Juan", headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert any(x["id"] == pid for x in data), \
            f"q=Juan (name) did not surface pago {pid}"

    def test_pagos_filter_fecha_range(self, admin_token, caja_token, estudiante_id, tipopago_id):
        eid, _ = estudiante_id
        today = date.today().isoformat()
        payload = {"id_estudiante": eid, "id_tipopago": tipopago_id, "cantidad": 1, "fecha_pago": today}
        rc = requests.post(f"{API}/pagos", json=payload, headers=auth_headers(caja_token))
        assert rc.status_code == 201
        pid = rc.json()["id"]
        r = requests.get(f"{API}/pagos?fecha_desde={today}&fecha_hasta={today}",
                         headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert any(p["id"] == pid for p in data)
        for p in data:
            assert p["fecha_pago"] == today

    def test_pagos_incluir_anulados_false(self, admin_token, caja_token, estudiante_id, tipopago_id):
        # create + anular one pago
        eid, _ = estudiante_id
        payload = {"id_estudiante": eid, "id_tipopago": tipopago_id, "cantidad": 1,
                   "fecha_pago": date.today().isoformat()}
        rc = requests.post(f"{API}/pagos", json=payload, headers=auth_headers(caja_token))
        assert rc.status_code == 201
        pid = rc.json()["id"]
        ra = requests.post(f"{API}/pagos/{pid}/anular", headers=auth_headers(admin_token))
        assert ra.status_code == 200

        r = requests.get(f"{API}/pagos?incluir_anulados=false", headers=auth_headers(admin_token))
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()]
        assert pid not in ids, "anulado pago should be filtered out"
        for p in r.json():
            assert p.get("anulado") is False

    def test_reportes_shape_and_sort(self, admin_token, caja_token, estudiante_id, tipopago_id):
        # Create 2 pagos in different dates within the year range
        eid, _ = estudiante_id
        d1 = "2026-03-15"
        d2 = "2026-03-16"
        for d in (d2, d1):  # insert out-of-order to verify aggregation sorts ASC
            rc = requests.post(f"{API}/pagos",
                               json={"id_estudiante": eid, "id_tipopago": tipopago_id,
                                     "cantidad": 1, "fecha_pago": d},
                               headers=auth_headers(caja_token))
            assert rc.status_code == 201

        r = requests.get(f"{API}/reportes?periodo=rango&desde=2026-03-01&hasta=2026-03-31",
                         headers=auth_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert {"desde", "hasta", "pagos", "totales"} <= set(data.keys())
        t = data["totales"]
        for k in ("validos", "anulados", "diferencia", "count_validos", "count_anulados"):
            assert k in t
        assert abs(t["diferencia"] - (t["validos"] - t["anulados"])) < 0.001

        # Hydrated fields in reportes pagos
        if data["pagos"]:
            sample = data["pagos"][0]
            for k in ("estudiante_nombre", "estudiante_ci", "tipopago_nombre"):
                assert k in sample, f"reportes pago missing {k}"

        # Sorted ASC by fecha_pago
        fps = [p["fecha_pago"] for p in data["pagos"]]
        assert fps == sorted(fps), f"reportes not sorted ASC by fecha_pago: {fps}"

    def test_reportes_created_by_filter(self, admin_token, caja_token, estudiante_id, tipopago_id):
        # Make sure there's at least one pago by caja in 2026
        eid, _ = estudiante_id
        requests.post(f"{API}/pagos",
                      json={"id_estudiante": eid, "id_tipopago": tipopago_id,
                            "cantidad": 1, "fecha_pago": "2026-05-10"},
                      headers=auth_headers(caja_token))
        ru = requests.get(f"{API}/users/list", headers=auth_headers(admin_token))
        caja_user = next((u for u in ru.json() if u["role"] == "caja" and u["name"] == "Test Caja"), None)
        assert caja_user
        r = requests.get(
            f"{API}/reportes?periodo=rango&desde=2026-01-01&hasta=2026-12-31&created_by={caja_user['id']}",
            headers=auth_headers(admin_token))
        assert r.status_code == 200
        for p in r.json()["pagos"]:
            assert p.get("created_by") == caja_user["id"]

    def test_post_pago_returns_hydrated_single(self, caja_token, estudiante_id, tipopago_id):
        """POST /api/pagos uses _hydrate_pago (not aggregation) — sanity-check shape."""
        eid, _ = estudiante_id
        rc = requests.post(f"{API}/pagos",
                           json={"id_estudiante": eid, "id_tipopago": tipopago_id,
                                 "cantidad": 1, "fecha_pago": date.today().isoformat()},
                           headers=auth_headers(caja_token))
        assert rc.status_code == 201
        p = rc.json()
        for k in ("estudiante_nombre", "estudiante_ci", "tipopago_nombre", "created_by_name"):
            assert k in p and p[k] is not None, f"POST /api/pagos missing {k}"

    def test_put_pago_returns_hydrated_single(self, admin_token, caja_token, estudiante_id, tipopago_id):
        """PUT /api/pagos/{id} uses _hydrate_pago — sanity-check shape."""
        eid, _ = estudiante_id
        rc = requests.post(f"{API}/pagos",
                           json={"id_estudiante": eid, "id_tipopago": tipopago_id,
                                 "cantidad": 2, "fecha_pago": date.today().isoformat()},
                           headers=auth_headers(caja_token))
        assert rc.status_code == 201
        pid = rc.json()["id"]
        ru = requests.put(f"{API}/pagos/{pid}", json={"cantidad": 4},
                          headers=auth_headers(admin_token))
        assert ru.status_code == 200
        p = ru.json()
        for k in ("estudiante_nombre", "estudiante_ci", "tipopago_nombre",
                  "created_by_name", "edited_by_name"):
            assert k in p
        assert p["created_by_name"] == "Test Caja"
        assert p["edited_by_name"]  # admin name set after edit

    def test_pagos_pago_with_null_edited_by_has_no_edited_name(
            self, admin_token, caja_token, estudiante_id, tipopago_id):
        """For un-edited pagos, edited_by_name should be None (not crash the aggregation)."""
        eid, _ = estudiante_id
        rc = requests.post(f"{API}/pagos",
                           json={"id_estudiante": eid, "id_tipopago": tipopago_id,
                                 "cantidad": 1, "fecha_pago": date.today().isoformat()},
                           headers=auth_headers(caja_token))
        assert rc.status_code == 201
        pid = rc.json()["id"]
        r = requests.get(f"{API}/pagos", headers=auth_headers(admin_token))
        assert r.status_code == 200
        found = next((p for p in r.json() if p["id"] == pid), None)
        assert found is not None
        # edited_by is null → edited_by_name should be null/None and edited_by None
        assert found.get("edited_by") in (None, "")
        assert found.get("edited_by_name") in (None, "")
