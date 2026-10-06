"""SQL Server 2025 FastAPI service for Comprobantes USFX.

Requires ``pyodbc`` and Microsoft ODBC Driver 18 for SQL Server
(``pip install pyodbc``).  Set SQLSERVER_CONNECTION_STRING, or set
SQLSERVER_HOST, SQLSERVER_DATABASE, SQLSERVER_USER and SQLSERVER_PASSWORD.
For Windows authentication use SQLSERVER_TRUSTED_AUTH=1.  Connections are
created lazily; importing this module never contacts a database.

Install Tablas.Sql on a freshly recreated database; legacy UUID SQL schemas
are not migrated. Entity keys use INT IDENTITY, including users and clients. User codes are separate unique
three-character alphanumeric codes (000 is reserved for the bootstrap SuperAdmin). JSON keeps
the shared frontend's field names and string IDs.
"""

from __future__ import annotations
import asyncio, json, os, re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal, Optional
import bcrypt, jwt, pyodbc
from fastapi import (
    FastAPI,
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from client_routes import SQLClientes, register_client_routes

BOLIVIA_TIMEZONE = timezone(timedelta(hours=-4))


def _format_response_date(value, field):
    if not isinstance(field, str):
        return value
    date_only = (
        field == "fecha"
        or field.startswith("fecha_")
        or field in {"desde", "hasta", "inicio", "fin"}
        or field.endswith("_date")
    )
    date_time = field.endswith(("_at", "_until"))
    if not date_only and not date_time:
        return value

    raw = value.isoformat() if isinstance(value, (datetime, date)) else value
    if not isinstance(raw, str):
        return value
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(.*)$", raw)
    if not match:
        return value
    year, month, day, suffix = match.groups()
    try:
        date(int(year), int(month), int(day))
    except ValueError:
        return value
    formatted = f"{day}/{month}/{year}"
    if date_time and suffix:
        return formatted + suffix.replace("T", " ", 1)
    return formatted


def _format_response_dates(value):
    if isinstance(value, dict):
        return {
            key: _format_response_dates(_format_response_date(item, key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_format_response_dates(item) for item in value]
    return value


class DateFormattedJSONResponse(JSONResponse):
    def render(self, content):
        return super().render(_format_response_dates(content))


load_dotenv()
app = FastAPI(
    title="Comprobantes USFX (SQL Server)",
    default_response_class=DateFormattedJSONResponse,
)
api = APIRouter(
    prefix="/api",
    default_response_class=DateFormattedJSONResponse,
)
security = HTTPBearer()
JWT_SECRET_KEY = os.getenv("JWT_SECRET") or os.getenv("SESSION_SECRET")
if not JWT_SECRET_KEY:
    raise RuntimeError("Configure JWT_SECRET o SESSION_SECRET para firmar sesiones.")
JWT_ALGORITHM = "HS256"
SUPER_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@usfx.bo").strip().lower()
SUPER_ADMIN_ROLE = "SuperAdmin"
ROLES = ("Administrador", "Caja", "Consultas")


class AnyModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class LoginRequest(AnyModel):
    email: EmailStr
    password: str


class UserCreate(AnyModel):
    codigo: str = Field(pattern=r"^[A-Za-z0-9]{3}$")
    email: EmailStr
    nombre: str
    password: str = Field(min_length=4)
    rol: str
    office_id: Optional[str] = None


class UserUpdate(AnyModel):
    codigo: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9]{3}$")
    email: Optional[EmailStr] = None
    nombre: Optional[str] = None
    rol: Optional[str] = None
    password: Optional[str] = None
    office_id: Optional[str] = None


class OfficeCreate(AnyModel):
    nombre: str
    prefijo_comprobante: str
    suboficina: str = ""
    activa: bool = True


class ClasificadorPresupuestarioCreate(AnyModel):
    codigo: str = Field(pattern=r"^[0-9]{5}$")
    nombre: str = Field(min_length=1, max_length=200)
    activa: bool = True


class TipoPagoCreate(AnyModel):
    codigo: str = Field(pattern=r"^[0-9]{5}$")
    nombre: str
    monto: Decimal
    descripcion: str = ""
    inicio: str
    fin: Optional[str] = None
    id_clasificador: int
    office_id: Optional[str] = None


class AmbienteCreate(AnyModel):
    nombre: str
    descripcion: str = ""
    horarios: list[dict] = Field(default_factory=list)
    turnos: list[dict] = Field(default_factory=list)
    office_id: Optional[str] = None


class TarifaCreate(AnyModel):
    ambiente_id: str
    nombre: str
    modalidad: Literal["hora", "manana", "tarde", "noche", "dia", "actividad"]
    monto: Decimal
    descripcion: str = ""
    desde: Optional[str] = None
    hasta: Optional[str] = None


class AlquilerCreate(AnyModel):
    ambiente_id: str
    tarifa_id: str
    fecha: str
    desde: Optional[str] = None
    hasta: Optional[str] = None
    cliente_id: str
    cobrar_ahora: bool = False
    office_id: Optional[str] = None


class PagoCreate(AnyModel):
    cliente_id: str
    fecha_pago: str
    office_id: Optional[str] = None
    id_tipo_pago: Optional[str] = None
    cantidad: Optional[float] = Field(default=None, gt=0)


class PagoItemCreate(AnyModel):
    id_tipo_pago: str
    cantidad: float = Field(gt=0)


def _connection_string():
    value = os.getenv("SQLSERVER_CONNECTION_STRING")
    if value:
        return value
    host = os.getenv("SQLSERVER_HOST", "localhost")
    db = os.getenv("SQLSERVER_DATABASE", "ComprobantesDB")
    if os.getenv("SQLSERVER_TRUSTED_AUTH", "").lower() in ("1", "true", "yes"):
        return f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={host};DATABASE={db};Trusted_Connection=yes;TrustServerCertificate=yes"
    return f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={host};DATABASE={db};UID={os.getenv('SQLSERVER_USER','')};PWD={os.getenv('SQLSERVER_PASSWORD','')};TrustServerCertificate=yes"


# Physical SQL identifiers differ from the stable JSON/API names used by both
# backends. Translate every statement, including transaction cursor statements,
# and normalize returned rows at the database boundary.
_SQL_COLUMNS = {
    "office_id": "id_oficina",
    "ambiente_id": "id_ambiente",
    "pago_id": "id_pago",
    "tarifa_id": "id_tarifa",
    "cliente_id": "id_cliente",
    "cliente_nombre": "nombre_cliente",
    "cliente_ci": "ci_cliente",
    "cliente_cu": "cu_cliente",
    "id_clasificador": "id_clasificador",
    "paid_by": "registrado_por",
    "claimed_at": "reservado_en",
    "alquiler_tramos": "alquiler_intervalos",
}
_API_COLUMNS = {physical: api_name for api_name, physical in _SQL_COLUMNS.items()}
_SQL_IDENTIFIER = re.compile(
    r"'(?:''|[^'])*'|--[^\n]*|/\*[\s\S]*?\*/|\b(" + "|".join(_SQL_COLUMNS) + r")\b",
    re.IGNORECASE,
)
_ID_COLUMNS = {
    "id", "office_id", "ambiente_id", "pago_id", "tarifa_id",
    "cliente_id", "id_tipo_pago", "id_clasificador", "alquiler_id", "origen_id", "created_by", "edited_by", "anulado_by", "paid_by",
}


def _physical_sql(statement):
    return _SQL_IDENTIFIER.sub(
        lambda match: _SQL_COLUMNS[match.group(1).lower()] if match.group(1) else match.group(),
        statement,
    )


class _SQLCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def execute(self, statement, *params):
        self._cursor.execute(_physical_sql(statement), *params)
        return self

    def _api_row(self, row):
        if row is None:
            return None
        return tuple(
            str(value) if isinstance(value, int)
            and _API_COLUMNS.get(column[0], column[0]) in _ID_COLUMNS else value
            for column, value in zip(self._cursor.description, row)
        )

    def fetchone(self):
        return self._api_row(self._cursor.fetchone())

    def fetchall(self):
        return [self._api_row(row) for row in self._cursor.fetchall()]


class _SQLConnection:
    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, *args):
        return self._connection.__exit__(*args)

    def cursor(self):
        return _SQLCursor(self._connection.cursor())


def _connect():
    return _SQLConnection(pyodbc.connect(_connection_string(), autocommit=False))


def _rows(cur):
    cols = [_API_COLUMNS.get(x[0], x[0]) for x in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _json(v):
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def clean(row):
    return {k: _json(v) for k, v in row.items()} if row else None


async def attach_office_names(rows):
    office_ids = list({row.get("office_id") for row in rows if row.get("office_id")})
    if not office_ids:
        return rows
    placeholders = ",".join("?" for _ in office_ids)
    offices = await sql(
        f"SELECT id,nombre FROM oficinas WHERE id IN ({placeholders})", office_ids
    )
    names = {row["id"]: row["nombre"] for row in offices}
    for row in rows:
        row["office_nombre"] = names.get(row.get("office_id"))
    return rows


async def sql(statement, params=(), *, one=False, write=False):
    def run():
        with _connect() as cn:
            cur = cn.cursor()
            cur.execute(statement, tuple(params))
            out = _rows(cur) if cur.description else []
            if one:
                out = out[0] if out else None
            if write:
                cn.commit()
            return clean(out) if one else [clean(x) for x in out]

    return await asyncio.to_thread(run)


async def tx(work):
    return await asyncio.to_thread(work)


def now():
    return datetime.now(timezone.utc).isoformat()


def minutes(text):
    if not isinstance(text, str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", text
    ):
        raise HTTPException(400, "La hora debe tener formato HH:MM.")
    return int(text[:2]) * 60 + int(text[3:])


def normalize_hhmm(value):
    if isinstance(value, time):
        if value.second or value.microsecond:
            raise HTTPException(400, "La hora debe tener formato HH:MM.")
        value = value.strftime("%H:%M")
    elif isinstance(value, str) and re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d:00", value
    ):
        value = value[:5]
    minutes(value)
    return value


def format_tariff_times(tariff):
    if tariff:
        for field in ("desde", "hasta"):
            if isinstance(tariff.get(field), time):
                tariff[field] = tariff[field].strftime("%H:%M")
    return tariff


def validate_blocks(blocks):
    by = {}
    for b in blocks:
        if b.get("dia") not in (
            "lunes",
            "martes",
            "miercoles",
            "jueves",
            "viernes",
            "sabado",
            "domingo",
        ):
            raise HTTPException(422, "Día inválido.")
        start, end = minutes(b.get("desde")), minutes(b.get("hasta"))
        if start >= end:
            raise HTTPException(422, "La hora de fin debe ser posterior al inicio.")
        by.setdefault(b["dia"], []).append((start, end))
    for values in by.values():
        values.sort()
        if any(b[0] < a[1] for a, b in zip(values, values[1:])):
            raise HTTPException(
                422, "Los horarios del mismo día no pueden superponerse."
            )


SHIFT_MODALITIES = ("manana", "tarde", "noche")


def validate_turnos(turnos, require_all=True):
    names = [block.get("turno") for block in turnos]
    if (
        any(not isinstance(name, str) for name in names)
        or len(names) != len(set(names))
        or any(name not in SHIFT_MODALITIES for name in names)
    ):
        raise HTTPException(422, "Cada turno debe configurarse una sola vez.")
    if require_all and set(names) != set(SHIFT_MODALITIES):
        raise HTTPException(422, "Configure los horarios de mañana, tarde y noche.")
    intervals = []
    normalized = []
    for block in turnos:
        start, end = block.get("desde"), block.get("hasta")
        if not isinstance(start, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start):
            raise HTTPException(422, "La hora de inicio de cada turno debe tener formato HH:MM.")
        if not isinstance(end, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", end):
            raise HTTPException(422, "La hora de fin de cada turno debe tener formato HH:MM.")
        first, last = minutes(start), minutes(end)
        if first >= last:
            raise HTTPException(422, "La hora de fin del turno debe ser posterior al inicio.")
        intervals.append((first, last))
        normalized.append({"turno": block["turno"], "desde": start, "hasta": end})
    intervals.sort()
    if any(current[0] < previous[1] for previous, current in zip(intervals, intervals[1:])):
        raise HTTPException(422, "Los turnos de un ambiente no pueden superponerse.")
    return normalized


async def room_turnos(ambiente_id):
    return await sql(
        "SELECT turno,CONVERT(varchar(5),desde,108) desde,CONVERT(varchar(5),hasta,108) hasta "
        "FROM ambiente_turnos WHERE ambiente_id=? ORDER BY desde",
        (ambiente_id,),
    )


def apply_current_shift(tariff, turnos):
    if tariff.get("modalidad") in SHIFT_MODALITIES:
        shift = next(
            (item for item in turnos if item["turno"] == tariff["modalidad"]),
            None,
        )
        if shift:
            tariff["desde"], tariff["hasta"] = shift["desde"], shift["hasta"]
    return format_tariff_times(tariff)


async def validate_tariff_shift(body):
    if body.modalidad not in SHIFT_MODALITIES:
        if body.desde is not None or body.hasta is not None:
            raise HTTPException(422, "Esta modalidad no admite horarios fijos.")
        return
    if not body.desde or not body.hasta:
        raise HTTPException(422, "Indique las horas definidas para el turno.")
    start, end = normalize_hhmm(body.desde), normalize_hhmm(body.hasta)
    if minutes(start) >= minutes(end):
        raise HTTPException(422, "La hora de fin debe ser posterior al inicio.")
    turnos = await room_turnos(body.ambiente_id)
    configured = next((item for item in turnos if item["turno"] == body.modalidad), None)
    if not configured:
        raise HTTPException(400, "Configure primero ese turno en el ambiente.")
    if (start, end) != (configured["desde"], configured["hasta"]):
        raise HTTPException(
            400,
            "El horario de la tarifa debe coincidir con el turno configurado en el ambiente.",
        )


def covered(blocks, start, end):
    s, e = minutes(start), minutes(end)
    values = sorted((minutes(x["desde"]), minutes(x["hasta"])) for x in blocks)
    merged = []
    for a, b in values:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return any(a <= s and b >= e for a, b in merged)


WEEKDAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")


def day_blocks(rows, day):
    index = WEEKDAYS.index(day) if isinstance(day, str) else int(day)
    return [
        {"desde": x["desde"], "hasta": x["hasta"]}
        for x in rows
        if (WEEKDAYS.index(x["dia"]) if isinstance(x["dia"], str) else int(x["dia"]))
        == index
    ]


def hashpw(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verifypw(password, hashed):
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def token(u):
    return jwt.encode(
        {
            "sub": u["id"],
            "email": u["email"],
            "rol": u["rol"],
            "exp": datetime.now(timezone.utc).timestamp() + 28800,
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def acquire_app_lock(c, resource):
    c.execute(
        "SET NOCOUNT ON; DECLARE @lock_result int; EXEC @lock_result=sys.sp_getapplock @Resource=?,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=5000; SELECT @lock_result;",
        (resource,),
    )
    result = c.fetchone()[0]
    if result < 0:
        raise HTTPException(
            409, "No se pudo obtener el bloqueo exclusivo; vuelva a intentarlo."
        )


async def current(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(
            credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
        )
        uid = payload["sub"]
    except Exception:
        raise HTTPException(401, "Token inválido.")
    u = await sql(
        "SELECT u.*,o.nombre office_nombre FROM usuarios u LEFT JOIN oficinas o ON o.id=u.office_id WHERE u.id=?",
        (uid,),
        one=True,
    )
    if not u:
        raise HTTPException(401, "Usuario no encontrado.")
    u.pop("password_hash", None)
    u.pop("email_key", None)
    return u


def roles(*allowed):
    async def dep(u=Depends(current)):
        if u["rol"] not in allowed and u["rol"] != SUPER_ADMIN_ROLE:
            raise HTTPException(403, "Sin permisos para esta acción.")
        return u

    return dep


async def office(u, requested=None, active=False):
    oid = requested if u["rol"] == SUPER_ADMIN_ROLE else u.get("office_id")
    if u["rol"] != "SuperAdmin" and requested and requested != oid:
        raise HTTPException(403, "Sin permisos para consultar otra oficina.")
    if not oid:
        raise HTTPException(400, "Seleccione una oficina.")
    q = "SELECT * FROM oficinas WHERE id=?" + (" AND activa=1" if active else "")
    if not await sql(q, (oid,), one=True):
        raise HTTPException(404, "Oficina no encontrada o inactiva.")
    return oid


def page(items, total, pag, tam):
    return {
        "items": items,
        "total": total,
        "page": pag,
        "size": tam,
        "pages": max(1, (total + tam - 1) // tam),
    }


async def office_scope_sql(u, requested=None, column="office_id"):
    if u["rol"] == SUPER_ADMIN_ROLE:
        if not requested:
            return "", []
        if not await sql("SELECT id FROM oficinas WHERE id=?", (requested,), one=True):
            raise HTTPException(404, "Oficina no encontrada.")
        return f"{column}=?", [requested]
    oid = u.get("office_id")
    if not oid:
        raise HTTPException(403, "El usuario no tiene una oficina asignada.")
    if requested and requested != oid:
        raise HTTPException(403, "Sin permisos para consultar otra oficina.")
    return f"{column}=?", [oid]


async def hydrate_rental(r):
    if not r:
        return r
    a = await sql(
        "SELECT nombre FROM ambientes WHERE id=?", (r["ambiente_id"],), one=True
    )
    t = await sql(
        "SELECT nombre,modalidad FROM tarifas_ambientes WHERE id=?",
        (r["tarifa_id"],),
        one=True,
    )
    r["ambiente_nombre"] = (a or {}).get("nombre")
    r["tarifa_nombre"] = (t or {}).get("nombre")
    r["modalidad"] = (t or {}).get("modalidad")
    r["tramos"] = await sql(
        "SELECT CONVERT(varchar(5),desde,108) desde,CONVERT(varchar(5),hasta,108) hasta FROM alquiler_intervalos WHERE alquiler_id=? ORDER BY desde",
        (r["id"],),
    )
    o = await sql(
        "SELECT nombre,suboficina,prefijo_comprobante FROM oficinas WHERE id=?",
        (r["office_id"],),
        one=True,
    )
    if o:
        r["office_nombre"] = o["nombre"]
        r["suboficina"] = o["suboficina"]
        r["prefijo_comprobante"] = (
            r.get("prefijo_comprobante") or o["prefijo_comprobante"]
        )
    r["comprobante_display"] = (
        f"{r['prefijo_comprobante']}-{r['cod_comprobante']} / {r['gestion']}"
        if r.get("prefijo_comprobante") and r.get("cod_comprobante")
        else None
    )
    if r.get("fecha_pago") is not None:
        r["fecha_pago"] = _json(r["fecha_pago"])
    r["created_at"] = _json(r["created_at"]) if r.get("created_at") else None
    return r


async def hydrate_environment(environment):
    if not environment:
        return environment
    await attach_office_names([environment])
    environment["horarios"] = await sql(
        "SELECT dia,CONVERT(varchar(5),desde,108) desde,CONVERT(varchar(5),hasta,108) hasta "
        "FROM ambiente_horarios WHERE ambiente_id=? ORDER BY dia,desde",
        (environment["id"],),
    )
    for block in environment["horarios"]:
        block["dia"] = WEEKDAYS[int(block["dia"])]
    environment["turnos"] = await sql(
        "SELECT turno,CONVERT(varchar(5),desde,108) desde,CONVERT(varchar(5),hasta,108) hasta "
        "FROM ambiente_turnos WHERE ambiente_id=? ORDER BY turno",
        (environment["id"],),
    )
    return environment


async def hydrate_payment(p):
    if not p:
        return p
    oid = p["office_id"]
    student = await sql(
        "SELECT nombre,ci,cu FROM clientes WHERE id=?",
        (p["cliente_id"],),
        one=True,
    )
    office_row = await sql(
        "SELECT nombre,suboficina,prefijo_comprobante FROM oficinas WHERE id=?",
        (oid,),
        one=True,
    )
    p["office_nombre"] = (office_row or {}).get("nombre")
    p["suboficina"] = (office_row or {}).get("suboficina", "")
    p["prefijo_comprobante"] = p.get("prefijo_comprobante") or (office_row or {}).get(
        "prefijo_comprobante"
    )
    p["comprobante_display"] = (
        f"{p['prefijo_comprobante']}-{p['cod_comprobante']} / {p['gestion']}"
        if p.get("prefijo_comprobante") and p.get("cod_comprobante")
        else None
    )
    p["cliente_nombre"] = (student or {}).get("nombre")
    p["cliente_ci"] = (student or {}).get("ci")
    p["cliente_cu"] = (student or {}).get("cu") or ""
    items = await sql(
        """SELECT i.id,i.id_tipo_pago,COALESCE(NULLIF(i.tipo_pago_nombre,N''),t.nombre) tipo_pago_nombre,
                              i.cantidad,i.monto,i.total
                       FROM pago_items i LEFT JOIN tipos_pagos t ON t.id=i.id_tipo_pago
                       WHERE i.pago_id=? ORDER BY i.id""",
        (p["id"],),
    )
    if not items and p.get("id_tipo_pago"):
        t = await sql(
            "SELECT nombre FROM tipos_pagos WHERE id=? AND office_id=?",
            (p["id_tipo_pago"], oid),
            one=True,
        )
        qty = float(p.get("cantidad") or 0)
        amount = float(p.get("monto") or 0)
        items = [
            {
                "id_tipo_pago": p["id_tipo_pago"],
                "tipo_pago_nombre": (t or {}).get("nombre"),
                "cantidad": qty,
                "monto": amount,
                "total": float(p.get("total") or qty * amount),
            }
        ]
    for item in items:
        item["cantidad"] = float(item.get("cantidad") or 0)
        item["monto"] = float(item.get("monto") or 0)
        item["total"] = float(
            item.get("total")
            if item.get("total") is not None
            else item["cantidad"] * item["monto"]
        )
    p["items"] = items
    p["estado"] = p.get("estado") or "emitido"
    p["anulado"] = bool(p.get("anulado"))
    p["total"] = sum(i["total"] for i in items) if items else float(p.get("total") or 0)
    if len(items) == 1:
        p["id_tipo_pago"] = items[0]["id_tipo_pago"]
        p["tipo_pago_nombre"] = items[0]["tipo_pago_nombre"]
        p["cantidad"] = items[0]["cantidad"]
        p["monto"] = items[0]["monto"]
    elif len(items) > 1:
        p["id_tipo_pago"] = None
        p["tipo_pago_nombre"] = "Varios conceptos"
        p["cantidad"] = None
        p["monto"] = 0
    else:
        p["id_tipo_pago"] = None
        p["tipo_pago_nombre"] = None
        p["cantidad"] = None
        p["monto"] = 0
    for field, output in (
        ("created_by", "created_by_name"),
        ("edited_by", "edited_by_name"),
    ):
        uid = p.get(field)
        user = (
            await sql("SELECT nombre FROM usuarios WHERE id=?", (uid,), one=True)
            if uid
            else None
        )
        p[output] = (user or {}).get("nombre")
    for field in ("created_at", "edited_at", "anulado_at"):
        if p.get(field) is not None:
            p[field] = _json(p[field])
    return p


def allocate_receipt(c, office_id, year, origin, origin_id):
    """Must be called inside the caller's transaction; one ledger spans both sources."""
    acquire_app_lock(c, f"receipt:{office_id}:{year}")
    c.execute(
        "SELECT prefijo_comprobante FROM oficinas WITH(HOLDLOCK) WHERE id=?",
        (office_id,),
    )
    prefix = c.fetchone()[0]
    c.execute(
        "SELECT siguiente FROM comprobante_contadores WITH(UPDLOCK,HOLDLOCK) WHERE office_id=? AND gestion=?",
        (office_id, year),
    )
    row = c.fetchone()
    if row is None:
        code = 1
        c.execute(
            "INSERT INTO comprobante_contadores(office_id,gestion,siguiente) VALUES(?,?,?)",
            (office_id, year, 2),
        )
    else:
        code = row[0]
        c.execute(
            "UPDATE comprobante_contadores SET siguiente=siguiente+1 WHERE office_id=? AND gestion=?",
            (office_id, year),
        )
    code = f"{code:05d}"
    c.execute(
        "INSERT INTO comprobante_asignaciones(office_id,gestion,codigo,origen,origen_id) VALUES(?,?,?,?,?)",
        (office_id, year, code, origin, origin_id),
    )
    return code, prefix


@api.post("/auth/login")
async def login(b: LoginRequest, response: Response):
    u = await sql(
        "SELECT * FROM usuarios WHERE email_key=LOWER(LTRIM(RTRIM(?)))",
        (str(b.email),),
        one=True,
    )
    if not u or not verifypw(b.password, u["password_hash"]):
        raise HTTPException(401, "Credenciales inválidas.")
    u.pop("password_hash", None)
    u.pop("email_key", None)
    u["office_nombre"] = (
        await sql("SELECT nombre FROM oficinas WHERE id=?", (u["office_id"],), one=True)
        or {}
    ).get("nombre")
    t = token(u)
    response.set_cookie("access_token", t, httponly=True, samesite="lax")
    return {"token": t, "usuario": u}


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}


@api.get("/auth/me")
async def me(u=Depends(current)):
    return u


@api.get("/oficinas")
async def offices(
    pag: int = Query(1, ge=1),
    tam: int = Query(20, ge=1, le=100),
    q: Optional[str] = None,
    u=Depends(current),
):
    where = "" if u["rol"] == "SuperAdmin" else " AND id=?"
    args = [] if u["rol"] == "SuperAdmin" else [u["office_id"]]
    if q:
        where += " AND nombre LIKE ?"
        args.append("%" + q.strip() + "%")
    total = (
        await sql("SELECT COUNT(*) n FROM oficinas WHERE 1=1" + where, args, one=True)
    )["n"]
    rows = await sql(
        "SELECT * FROM oficinas WHERE 1=1"
        + where
        + " ORDER BY nombre OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        args + [(pag - 1) * tam, tam],
    )
    return page(rows, total, pag, tam)


@api.post("/oficinas", status_code=201)
async def create_office(b: OfficeCreate, u=Depends(roles(SUPER_ADMIN_ROLE))):
    name = b.nombre.strip()
    prefix = b.prefijo_comprobante.strip().upper()
    if not name:
        raise HTTPException(400, "Ingrese el nombre de la oficina.")
    if not re.fullmatch(r"[A-Z]{3}", prefix):
        raise HTTPException(400, "El prefijo del comprobante debe tener tres letras.")
    oid = (await sql(
        "INSERT INTO oficinas(nombre,prefijo_comprobante,suboficina,activa) OUTPUT INSERTED.id VALUES(?,?,?,?)",
        (name, prefix, b.suboficina.strip(), b.activa),
        one=True, write=True,
    ))["id"]
    return await sql("SELECT * FROM oficinas WHERE id=?", (oid,), one=True)


@api.put("/oficinas/{oid}")
async def update_office(oid: str, b: OfficeCreate, u=Depends(roles(SUPER_ADMIN_ROLE))):
    if not await sql("SELECT id FROM oficinas WHERE id=?", (oid,), one=True):
        raise HTTPException(404, "Oficina no encontrada.")
    name = b.nombre.strip()
    prefix = b.prefijo_comprobante.strip().upper()
    if not name:
        raise HTTPException(400, "Ingrese el nombre de la oficina.")
    if not re.fullmatch(r"[A-Z]{3}", prefix):
        raise HTTPException(400, "El prefijo del comprobante debe tener tres letras.")
    await sql(
        "UPDATE oficinas SET nombre=?,prefijo_comprobante=?,suboficina=?,activa=? WHERE id=?",
        (name, prefix, b.suboficina.strip(), b.activa, oid),
        write=True,
    )
    return await sql("SELECT * FROM oficinas WHERE id=?", (oid,), one=True)


@api.delete("/oficinas/{oid}")
async def delete_office(oid: str, u=Depends(roles(SUPER_ADMIN_ROLE))):
    if not await sql("SELECT id FROM oficinas WHERE id=?", (oid,), one=True):
        raise HTTPException(404, "Oficina no encontrada.")
    checks = (
        "usuarios",
        "tipos_pagos",
        "ambientes",
        "tarifas_ambientes",
        "pagos",
        "alquileres",
        "comprobante_contadores",
        "comprobante_asignaciones",
    )
    for table in checks:
        if await sql(
            f"SELECT TOP 1 1 existe FROM {table} WHERE office_id=?", (oid,), one=True
        ):
            raise HTTPException(
                400, "No se puede eliminar una oficina con registros asociados."
            )
    await sql("DELETE FROM oficinas WHERE id=?", (oid,), write=True)
    return {"ok": True}


@api.get("/usuarios")
async def users(
    pag: int = Query(1, ge=1),
    tam: int = Query(10, ge=1, le=100),
    office_id: Optional[str] = None,
    u=Depends(roles("SuperAdmin")),
):
    scope, args = await office_scope_sql(u, office_id)
    where = ("WHERE " + scope) if scope else ""
    total = (await sql("SELECT COUNT(*) n FROM usuarios " + where, args, one=True))["n"]
    rows = await sql(
        "SELECT id,codigo,email,nombre,rol,office_id,created_at FROM usuarios "
        + where
        + " ORDER BY nombre OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        args + [(pag - 1) * tam, tam],
    )
    return page(await attach_office_names(rows), total, pag, tam)


@api.get("/usuarios/list")
async def users_admin_list(office_id: Optional[str] = None, u=Depends(roles("SuperAdmin"))):
    return await users_list(office_id, u)


@api.get("/reportes/registradores")
async def users_list(office_id: Optional[str] = None, u=Depends(current)):
    scope, args = await office_scope_sql(u, office_id)
    where = (" WHERE " + scope) if scope else ""
    return await attach_office_names(
        await sql(
            "SELECT id,codigo,nombre,rol,office_id FROM usuarios" + where + " ORDER BY nombre",
            args,
        )
    )


@api.post("/usuarios", status_code=201)
async def create_user(b: UserCreate, u=Depends(roles("SuperAdmin"))):
    oid = await office(u, b.office_id, True)
    if b.rol not in ROLES:
        raise HTTPException(422, "Rol inválido.")
    email = str(b.email).strip().lower()
    if email == SUPER_ADMIN_EMAIL or await sql(
        "SELECT id FROM usuarios WHERE email_key=LOWER(LTRIM(RTRIM(?)))",
        (email,),
        one=True,
    ):
        raise HTTPException(400, "El email ya está registrado.")
    if b.rol == "Administrador" and u["rol"] != SUPER_ADMIN_ROLE:
        raise HTTPException(403, "Sólo el Super Admin asigna administradores.")
    if b.rol == "Administrador" and await sql(
        "SELECT id FROM usuarios WHERE office_id=? AND rol=N'Administrador'",
        (oid,),
        one=True,
    ):
        raise HTTPException(400, "La oficina ya tiene un administrador.")
    if b.codigo == "000" or await sql("SELECT id FROM usuarios WHERE codigo=?", (b.codigo,), one=True):
        raise HTTPException(400, "El código de usuario ya está reservado o registrado.")
    ident = (await sql(
        "INSERT INTO usuarios(codigo,email,nombre,rol,office_id,password_hash) OUTPUT INSERTED.id VALUES(?,?,?,?,?,?)",
        (b.codigo, email, b.nombre, b.rol, oid, hashpw(b.password)),
        one=True, write=True,
    ))["id"]
    return (
        await attach_office_names(
            [
                await sql(
                    "SELECT id,codigo,email,nombre,rol,office_id,created_at FROM usuarios WHERE id=?",
                    (ident,),
                    one=True,
                )
            ]
        )
    )[0]


@api.put("/usuarios/{uid}")
async def update_user(uid: str, b: UserUpdate, u=Depends(roles("SuperAdmin"))):
    target = await sql("SELECT * FROM usuarios WHERE id=?", (uid,), one=True)
    if not target:
        raise HTTPException(404, "Usuario no encontrado.")
    oid = target["office_id"]
    if oid:
        await office_scope_sql(u, oid)
    elif u["rol"] != SUPER_ADMIN_ROLE:
        raise HTTPException(403, "Sin permisos para modificar este usuario.")
    if target["rol"] == SUPER_ADMIN_ROLE:
        raise HTTPException(403, "La cuenta del Super Admin está protegida.")
    if b.codigo is not None and b.codigo != target["codigo"]:
        raise HTTPException(400, "El código de usuario no se puede cambiar.")
    if (
        u["rol"] != SUPER_ADMIN_ROLE
        and target["rol"] == "Administrador"
        and uid != u["id"]
    ):
        raise HTTPException(403, "No puede modificar administradores.")
    if b.rol is not None and b.rol not in ROLES:
        raise HTTPException(422, "Rol inválido.")
    if b.rol == "Administrador" and u["rol"] != SUPER_ADMIN_ROLE and uid != u["id"]:
        raise HTTPException(403, "Sólo el Super Admin asigna administradores.")
    if (
        u["rol"] != SUPER_ADMIN_ROLE
        and uid == u["id"]
        and b.rol is not None
        and b.rol != target["rol"]
    ):
        raise HTTPException(403, "No puede cambiar su propio rol.")
    sets = []
    args = []
    if b.email is not None:
        email = str(b.email).strip().lower()
        if await sql("SELECT id FROM usuarios WHERE email_key=LOWER(?) AND id<>?", (email, uid), one=True):
            raise HTTPException(400, "El email ya está registrado.")
        sets.append("email=?")
        args.append(email)
    for col, val in (("nombre", b.nombre), ("rol", b.rol), ("office_id", b.office_id)):
        if col == "office_id" and val is not None:
            val = await office(u, val, True)
        if val is not None:
            sets.append(col + "=?")
            args.append(val)
    if b.password:
        sets.append("password_hash=?")
        args.append(hashpw(b.password))
    if not sets:
        raise HTTPException(400, "Sin cambios.")
    resulting_office = next(
        (args[i] for i, x in enumerate(sets) if x == "office_id=?"), oid
    )
    resulting_role = b.rol or target["rol"]
    if resulting_role in ROLES and not resulting_office:
        raise HTTPException(400, "Seleccione una oficina para el usuario.")
    if resulting_role == "Administrador" and (
        resulting_office != oid or target["rol"] != "Administrador"
    ):
        if u["rol"] != SUPER_ADMIN_ROLE:
            raise HTTPException(403, "Sólo el Super Admin asigna administradores.")
        if await sql(
            "SELECT id FROM usuarios WHERE office_id=? AND rol=N'Administrador' AND id<>?",
            (resulting_office, uid),
            one=True,
        ):
            raise HTTPException(400, "La oficina ya tiene un administrador.")
    args.append(uid)
    await sql(
        "UPDATE usuarios SET " + ",".join(sets) + " WHERE id=?", tuple(args), write=True
    )
    return (
        await attach_office_names(
            [
                await sql(
                    "SELECT id,codigo,email,nombre,rol,office_id,created_at FROM usuarios WHERE id=?",
                    (uid,),
                    one=True,
                )
            ]
        )
    )[0]


@api.delete("/usuarios/{uid}")
async def delete_user(uid: str, u=Depends(roles("SuperAdmin"))):
    if uid == u["id"]:
        raise HTTPException(400, "No puedes eliminar tu propio usuario.")
    target = await sql(
        "SELECT rol,email,office_id FROM usuarios WHERE id=?", (uid,), one=True
    )
    if not target:
        raise HTTPException(404, "Usuario no encontrado.")
    if (
        target["rol"] == SUPER_ADMIN_ROLE
        or target["email"].lower() == SUPER_ADMIN_EMAIL
    ):
        raise HTTPException(400, "No puedes eliminar el Super Admin.")
    if target["office_id"]:
        await office_scope_sql(u, target["office_id"])
    elif u["rol"] != SUPER_ADMIN_ROLE:
        raise HTTPException(403, "Sin permisos para eliminar este usuario.")
    if target["rol"] == "Administrador" and u["rol"] != SUPER_ADMIN_ROLE:
        raise HTTPException(403, "Sólo el Super Admin puede eliminar administradores.")
    # Preserve the owner of historical receipts, even with generated primary keys.
    if await sql(
        """SELECT TOP 1 1 usado FROM pagos WHERE created_by=? OR edited_by=? OR anulado_by=?
           UNION ALL SELECT TOP 1 1 usado FROM alquileres WHERE paid_by=?""",
        (uid, uid, uid, uid), one=True,
    ):
        raise HTTPException(400, "No se puede eliminar un usuario registrado en el historial de comprobantes.")
    await sql("DELETE FROM usuarios WHERE id=?", (uid,), write=True)
    return {"ok": True}


async def listing(table, fields, office_id, u, pag, tam, q=None, activos=False):
    scope, args = await office_scope_sql(u, office_id, "office_id")
    where = scope or "1=1"
    if q:
        searchable = {
            "clientes": "(nombre LIKE ? OR ci LIKE ? OR cu LIKE ?)",
            "tipos_pagos": "nombre LIKE ?",
            "ambientes": "nombre LIKE ?",
        }[table]
        where += " AND " + searchable
        args += ["%" + q + "%"] * (searchable.count("?"))
    if activos and table == "tipos_pagos":
        today = date.today().isoformat()
        where += " AND inicio<=? AND (fin IS NULL OR fin>=?)"
        args.extend([today, today])
    total = (
        await sql(f"SELECT COUNT(*) n FROM {table} WHERE {where}", args, one=True)
    )["n"]
    ordering = {
        "clientes": "nombre,cu",
        "tipos_pagos": "nombre,inicio DESC",
        "ambientes": "nombre_key,nombre",
    }.get(table, "nombre")
    rows = await sql(
        f"SELECT {fields} FROM {table} WHERE {where} ORDER BY {ordering} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        args + [(pag - 1) * tam, tam],
    )
    await attach_office_names(rows)
    return page(rows, total, pag, tam)


@api.get("/clasificadores-presupuestarios")
async def budget_classifiers(
    pag: int = Query(1, ge=1),
    tam: int = Query(1, ge=1, le=100),
    activos: bool = False,
    u=Depends(current),
):
    where = " WHERE activa=1" if activos else ""
    total = (
        await sql(
            "SELECT COUNT(*) n FROM clasificadores_presupuestarios" + where,
            (), one=True,
        )
    )["n"]
    rows = await sql(
        "SELECT id,codigo,nombre,activa FROM clasificadores_presupuestarios"
        + where
        + " ORDER BY codigo OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        ((pag - 1) * tam, tam),
    )
    return page(rows, total, pag, tam)


@api.post("/clasificadores-presupuestarios", status_code=201)
async def create_budget_classifier(
    b: ClasificadorPresupuestarioCreate,
    u=Depends(roles(SUPER_ADMIN_ROLE)),
):
    name = b.nombre.strip()
    if not name:
        raise HTTPException(400, "Ingrese el nombre del clasificador.")
    if await sql(
        "SELECT id FROM clasificadores_presupuestarios WHERE codigo=?",
        (b.codigo,), one=True,
    ):
        raise HTTPException(400, "El código del clasificador ya existe.")
    return await sql(
        "INSERT INTO clasificadores_presupuestarios(codigo,nombre,activa) "
        "OUTPUT INSERTED.id,INSERTED.codigo,INSERTED.nombre,INSERTED.activa "
        "VALUES(?,?,?)",
        (b.codigo, name, b.activa), one=True, write=True,
    )


@api.put("/clasificadores-presupuestarios/{cid}")
async def update_budget_classifier(
    cid: str,
    b: ClasificadorPresupuestarioCreate,
    u=Depends(roles(SUPER_ADMIN_ROLE)),
):
    name = b.nombre.strip()
    if not name:
        raise HTTPException(400, "Ingrese el nombre del clasificador.")
    duplicate = await sql(
        "SELECT id FROM clasificadores_presupuestarios WHERE codigo=? AND id<>?",
        (b.codigo, cid), one=True,
    )
    if duplicate:
        raise HTTPException(400, "El código del clasificador ya existe.")
    result = await sql(
        "UPDATE clasificadores_presupuestarios SET codigo=?,nombre=?,activa=? "
        "OUTPUT INSERTED.id,INSERTED.codigo,INSERTED.nombre,INSERTED.activa WHERE id=?",
        (b.codigo, name, b.activa, cid), one=True, write=True,
    )
    if not result:
        raise HTTPException(404, "Clasificador no encontrado.")
    return result


async def active_classifier_sql(classifier_id):
    classifier = await sql(
        "SELECT id FROM clasificadores_presupuestarios WHERE id=? AND activa=1",
        (classifier_id,), one=True,
    )
    if not classifier:
        raise HTTPException(400, "Seleccione un clasificador presupuestario activo.")


async def concept_with_classifier(tid):
    row = await sql(
        """SELECT t.id,t.codigo,t.nombre,t.monto,t.descripcion,t.inicio,t.fin,
                  t.id_clasificador,t.office_id,c.codigo clasificador_codigo,
                  c.nombre clasificador_nombre,c.activa clasificador_activa
           FROM tipos_pagos t LEFT JOIN clasificadores_presupuestarios c
             ON c.id=t.id_clasificador WHERE t.id=?""",
        (tid,), one=True,
    )
    if not row:
        return None
    return (await attach_office_names([row]))[0]


@api.get("/conceptos-recaudacion")
@api.get("/tipos-pagos")
async def concepts(
    pag: int = Query(1, ge=1),
    tam: int = Query(10, ge=1, le=100),
    activos: bool = False,
    office_id: Optional[str] = None,
    u=Depends(current),
):
    scope, args = await office_scope_sql(u, office_id, "t.office_id")
    where = scope or "1=1"
    if activos:
        today = date.today().isoformat()
        where += (
            " AND t.inicio<=? AND (t.fin IS NULL OR t.fin>=?)"
            " AND t.codigo IS NOT NULL AND t.id_clasificador IS NOT NULL"
            " AND c.activa=1"
        )
        args.extend([today, today])
    joins = (
        " FROM tipos_pagos t LEFT JOIN clasificadores_presupuestarios c"
        " ON c.id=t.id_clasificador"
    )
    total = (await sql(
        "SELECT COUNT(*) n" + joins + " WHERE " + where,
        args, one=True,
    ))["n"]
    rows = await sql(
        """SELECT t.id,t.codigo,t.nombre,t.monto,t.descripcion,t.inicio,t.fin,
                  t.id_clasificador,t.office_id,c.codigo clasificador_codigo,
                  c.nombre clasificador_nombre,c.activa clasificador_activa"""
        + joins + " WHERE " + where
        + " ORDER BY t.nombre,t.inicio DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        args + [(pag - 1) * tam, tam],
    )
    await attach_office_names(rows)
    return page(rows, total, pag, tam)


@api.post("/conceptos-recaudacion", status_code=201)
@api.post("/tipos-pagos", status_code=201)
async def create_concept(b: TipoPagoCreate, u=Depends(roles("Administrador"))):
    oid = await office(u, b.office_id, True)
    name = b.nombre.strip()
    if not name:
        raise HTTPException(400, "Ingrese el nombre del concepto.")
    await active_classifier_sql(b.id_clasificador)
    duplicate = await sql(
        "SELECT id FROM tipos_pagos WHERE office_id=? AND codigo=?",
        (oid, b.codigo), one=True,
    )
    if duplicate:
        raise HTTPException(400, "El código del concepto ya existe en esta oficina.")
    ident = (await sql(
        """INSERT INTO tipos_pagos
             (office_id,codigo,id_clasificador,nombre,monto,descripcion,inicio,fin)
           OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?)""",
        (oid, b.codigo, b.id_clasificador, name, b.monto, b.descripcion, b.inicio, b.fin),
        one=True, write=True,
    ))["id"]
    return await concept_with_classifier(ident)


@api.put("/conceptos-recaudacion/{tid}")
@api.put("/tipos-pagos/{tid}")
async def update_concept(
    tid: str, b: TipoPagoCreate, u=Depends(roles("Administrador"))
):
    target = await sql("SELECT office_id FROM tipos_pagos WHERE id=?", (tid,), one=True)
    if not target:
        raise HTTPException(404, "Concepto no encontrado.")
    oid = target["office_id"]
    await office_scope_sql(u, oid)
    if b.office_id and b.office_id != oid:
        raise HTTPException(400, "No se puede cambiar la oficina del concepto.")
    name = b.nombre.strip()
    if not name:
        raise HTTPException(400, "Ingrese el nombre del concepto.")
    await active_classifier_sql(b.id_clasificador)
    duplicate = await sql(
        "SELECT id FROM tipos_pagos WHERE office_id=? AND codigo=? AND id<>?",
        (oid, b.codigo, tid), one=True,
    )
    if duplicate:
        raise HTTPException(400, "El código del concepto ya existe en esta oficina.")
    await sql(
        """UPDATE tipos_pagos SET codigo=?,id_clasificador=?,nombre=?,monto=?,
             descripcion=?,inicio=?,fin=? WHERE id=? AND office_id=?""",
        (b.codigo, b.id_clasificador, name, b.monto, b.descripcion, b.inicio, b.fin, tid, oid),
        write=True,
    )
    return await concept_with_classifier(tid)


@api.delete("/conceptos-recaudacion/{tid}")
@api.delete("/tipos-pagos/{tid}")
async def delete_concept(tid: str, u=Depends(roles("Administrador"))):
    target = await sql("SELECT office_id FROM tipos_pagos WHERE id=?", (tid,), one=True)
    if not target:
        raise HTTPException(404, "Concepto no encontrado.")
    await office_scope_sql(u, target["office_id"])
    if await sql(
        """SELECT TOP 1 p.id FROM pagos p
                    WHERE p.office_id=? AND (p.id_tipo_pago=? OR EXISTS(
                      SELECT 1 FROM pago_items i WHERE i.pago_id=p.id AND i.id_tipo_pago=?))""",
        (target["office_id"], tid, tid),
        one=True,
    ):
        raise HTTPException(400, "No se puede eliminar: tiene pagos registrados.")
    await sql(
        "DELETE FROM tipos_pagos WHERE id=? AND office_id=?",
        (tid, target["office_id"]),
        write=True,
    )
    return {"ok": True}


@api.get("/ambientes")
async def environments(
    pag: int = Query(1, ge=1),
    tam: int = Query(20, ge=1, le=100),
    q: Optional[str] = None,
    office_id: Optional[str] = None,
    u=Depends(roles("Administrador", "Caja")),
):
    result = await listing(
        "ambientes",
        "id,nombre,descripcion,office_id,created_at",
        office_id,
        u,
        pag,
        tam,
        q,
    )
    for i, x in enumerate(result["items"]):
        result["items"][i] = await hydrate_environment(x)
    return result


@api.post("/ambientes", status_code=201)
async def create_environment(b: AmbienteCreate, u=Depends(roles("Administrador"))):
    validate_blocks(b.horarios)
    turnos = validate_turnos(b.turnos)
    oid = await office(u, b.office_id, True)
    name = b.nombre.strip()
    if not name:
        raise HTTPException(400, "Ingrese el nombre del ambiente.")

    def create():
        with _connect() as cn:
            c = cn.cursor()
            c.execute(
                "INSERT INTO ambientes(office_id,nombre,descripcion) OUTPUT INSERTED.id VALUES(?,?,?)",
                (oid, name, b.descripcion),
            )
            ident = c.fetchone()[0]
            for h in b.horarios:
                c.execute(
                    "INSERT INTO ambiente_horarios(ambiente_id,dia,desde,hasta) VALUES(?,?,?,?)",
                    (ident, WEEKDAYS.index(h["dia"]), h["desde"], h["hasta"]),
                )
            for turno in turnos:
                c.execute(
                    "INSERT INTO ambiente_turnos(ambiente_id,turno,desde,hasta) VALUES(?,?,?,?)",
                    (ident, turno["turno"], turno["desde"], turno["hasta"]),
                )
            cn.commit()
            return ident

    ident = await tx(create)
    return await hydrate_environment(
        await sql("SELECT * FROM ambientes WHERE id=?", (ident,), one=True)
    )


@api.put("/ambientes/{aid}")
async def update_environment(
    aid: str, b: AmbienteCreate, u=Depends(roles("Administrador"))
):
    validate_blocks(b.horarios)
    turnos = (
        validate_turnos(b.turnos)
        if "turnos" in b.model_fields_set
        else None
    )
    room = await sql("SELECT office_id FROM ambientes WHERE id=?", (aid,), one=True)
    if not room:
        raise HTTPException(404, "Ambiente no encontrado.")
    await office_scope_sql(u, room["office_id"])
    if b.office_id and b.office_id != room["office_id"]:
        raise HTTPException(400, "No se puede cambiar la oficina del ambiente.")
    name = b.nombre.strip()
    if not name:
        raise HTTPException(400, "Ingrese el nombre del ambiente.")

    def update():
        with _connect() as cn:
            c = cn.cursor()
            acquire_app_lock(c, f"room-config:{aid}")
            c.execute(
                """SELECT DISTINCT a.fecha FROM alquileres a WITH(UPDLOCK,HOLDLOCK)
                         WHERE a.ambiente_id=? AND a.fecha>=?
                         AND a.estado IN(N'confirmando',N'reservado',N'procesando',N'pagado')""",
                (aid, date.today()),
            )
            future = [row[0] for row in c.fetchall()]
            for reserved_date in future:
                c.execute(
                    """SELECT t.desde,t.hasta FROM alquiler_intervalos t
                             JOIN alquileres a ON a.id=t.alquiler_id
                             WHERE a.ambiente_id=? AND a.fecha=? AND a.estado<>N'cancelado'""",
                    (aid, reserved_date),
                )
                existing = c.fetchall()
                blocks = day_blocks(b.horarios, reserved_date.weekday())
                if any(
                    not covered(blocks, str(x[0])[:5], str(x[1])[:5]) for x in existing
                ):
                    raise HTTPException(
                        400, "El nuevo horario no cubre una reserva futura."
                    )
            c.execute(
                "UPDATE ambientes SET nombre=?,descripcion=? WHERE id=? AND office_id=?",
                (name, b.descripcion, aid, room["office_id"]),
            )
            if not c.rowcount:
                raise HTTPException(404, "Ambiente no encontrado.")
            c.execute("DELETE FROM ambiente_horarios WHERE ambiente_id=?", (aid,))
            for h in b.horarios:
                c.execute(
                    "INSERT INTO ambiente_horarios(ambiente_id,dia,desde,hasta) VALUES(?,?,?,?)",
                    (aid, WEEKDAYS.index(h["dia"]), h["desde"], h["hasta"]),
                )
            if turnos is not None:
                c.execute("DELETE FROM ambiente_turnos WHERE ambiente_id=?", (aid,))
                for turno in turnos:
                    c.execute(
                        "INSERT INTO ambiente_turnos(ambiente_id,turno,desde,hasta) VALUES(?,?,?,?)",
                        (aid, turno["turno"], turno["desde"], turno["hasta"]),
                    )
            cn.commit()

    await tx(update)
    return await hydrate_environment(
        await sql("SELECT * FROM ambientes WHERE id=?", (aid,), one=True)
    )


@api.delete("/ambientes/{aid}")
async def delete_environment(aid: str, u=Depends(roles("Administrador"))):
    room = await sql("SELECT office_id FROM ambientes WHERE id=?", (aid,), one=True)
    if not room:
        raise HTTPException(404, "Ambiente no encontrado.")
    await office_scope_sql(u, room["office_id"])

    def delete():
        with _connect() as cn:
            c = cn.cursor()
            acquire_app_lock(c, f"room-config:{aid}")
            c.execute(
                "SELECT office_id FROM ambientes WITH(UPDLOCK,HOLDLOCK) WHERE id=?",
                (aid,),
            )
            current_room = c.fetchone()
            if not current_room:
                raise HTTPException(404, "Ambiente no encontrado.")
            c.execute(
                "SELECT TOP 1 id FROM alquileres WHERE ambiente_id=? AND estado IN(N'confirmando',N'reservado',N'procesando',N'pagado')",
                (aid,),
            )
            if c.fetchone():
                raise HTTPException(
                    400, "No se puede eliminar un ambiente con alquileres activos."
                )
            c.execute(
                "SELECT TOP 1 id FROM tarifas_ambientes WHERE ambiente_id=?", (aid,)
            )
            if c.fetchone():
                raise HTTPException(
                    400, "Elimine primero las tarifas asociadas al ambiente."
                )
            c.execute("DELETE FROM ocupacion_intervalos WHERE ambiente_id=?", (aid,))
            c.execute("DELETE FROM ambiente_ocupacion WHERE ambiente_id=?", (aid,))
            c.execute("DELETE FROM ambiente_turnos WHERE ambiente_id=?", (aid,))
            c.execute("DELETE FROM ambiente_horarios WHERE ambiente_id=?", (aid,))
            c.execute(
                "DELETE FROM ambientes WHERE id=? AND office_id=?",
                (aid, current_room[0]),
            )
            if not c.rowcount:
                raise HTTPException(
                    409, "No se pudo eliminar el ambiente; vuelva a intentarlo."
                )
            cn.commit()

    await tx(delete)
    return {"ok": True}


@api.get("/tarifas-ambientes")
async def tariffs(ambiente_id: str, u=Depends(roles("Administrador", "Caja"))):
    room = await sql(
        "SELECT office_id FROM ambientes WHERE id=?", (ambiente_id,), one=True
    )
    if not room:
        raise HTTPException(404, "Ambiente no encontrado.")
    await office_scope_sql(u, room["office_id"])
    rows = await sql(
        "SELECT * FROM tarifas_ambientes WHERE ambiente_id=? ORDER BY nombre",
        (ambiente_id,),
    )
    turnos = await room_turnos(ambiente_id)
    return [apply_current_shift(row, turnos) for row in rows]


@api.post("/tarifas-ambientes", status_code=201)
async def create_tariff(b: TarifaCreate, u=Depends(roles("Administrador"))):
    room = await sql(
        "SELECT office_id FROM ambientes WHERE id=?", (b.ambiente_id,), one=True
    )
    if not room:
        raise HTTPException(404, "Ambiente no encontrado.")
    await office_scope_sql(u, room["office_id"])
    await validate_tariff_shift(b)
    ident = (await sql(
        "INSERT INTO tarifas_ambientes(ambiente_id,office_id,nombre,modalidad,monto,descripcion,desde,hasta) OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?)",
        (
            b.ambiente_id,
            room["office_id"],
            b.nombre,
            b.modalidad,
            b.monto,
            b.descripcion,
            b.desde,
            b.hasta,
        ),
        one=True, write=True,
    ))["id"]
    tariff = await sql("SELECT * FROM tarifas_ambientes WHERE id=?", (ident,), one=True)
    return apply_current_shift(tariff, await room_turnos(b.ambiente_id))


@api.put("/tarifas-ambientes/{tid}")
async def update_tariff(tid: str, b: TarifaCreate, u=Depends(roles("Administrador"))):
    target = await sql(
        "SELECT ambiente_id,office_id FROM tarifas_ambientes WHERE id=?",
        (tid,),
        one=True,
    )
    if not target:
        raise HTTPException(404, "Tarifa no encontrada.")
    await office_scope_sql(u, target["office_id"])
    if b.ambiente_id != target["ambiente_id"]:
        raise HTTPException(400, "No se puede cambiar el ambiente de una tarifa.")
    await validate_tariff_shift(b)
    await sql(
        "UPDATE tarifas_ambientes SET nombre=?,modalidad=?,monto=?,descripcion=?,desde=?,hasta=? WHERE id=? AND office_id=?",
        (
            b.nombre,
            b.modalidad,
            b.monto,
            b.descripcion,
            b.desde,
            b.hasta,
            tid,
            target["office_id"],
        ),
        write=True,
    )
    tariff = await sql("SELECT * FROM tarifas_ambientes WHERE id=?", (tid,), one=True)
    return apply_current_shift(tariff, await room_turnos(target["ambiente_id"]))


@api.delete("/tarifas-ambientes/{tid}")
async def delete_tariff(tid: str, u=Depends(roles("Administrador"))):
    target = await sql(
        "SELECT office_id FROM tarifas_ambientes WHERE id=?", (tid,), one=True
    )
    if not target:
        raise HTTPException(404, "Tarifa no encontrada.")
    await office_scope_sql(u, target["office_id"])
    await sql(
        "DELETE FROM tarifas_ambientes WHERE id=? AND office_id=?",
        (tid, target["office_id"]),
        write=True,
    )
    return {"ok": True}


@api.get("/alquileres")
async def rentals(
    ambiente_id: str,
    fecha_desde: str,
    fecha_hasta: str,
    office_id: Optional[str] = None,
    u=Depends(roles("Administrador", "Caja", "Consultas")),
):
    start = parse_iso_date(fecha_desde, "La fecha debe tener formato YYYY-MM-DD.")
    end = parse_iso_date(fecha_hasta, "La fecha debe tener formato YYYY-MM-DD.")
    if end < start or (end - start).days > 366:
        raise HTTPException(400, "Rango de fechas inválido.")
    room = await sql(
        "SELECT office_id FROM ambientes WHERE id=?", (ambiente_id,), one=True
    )
    if not room:
        raise HTTPException(404, "Ambiente no encontrado en esa oficina.")
    await office_scope_sql(u, office_id or room["office_id"])
    if office_id and office_id != room["office_id"]:
        raise HTTPException(404, "Ambiente no encontrado en esa oficina.")
    rows = await sql(
        "SELECT * FROM alquileres WHERE ambiente_id=? AND fecha>=? AND fecha<=? AND estado<>N'confirmando' ORDER BY fecha,created_at",
        (ambiente_id, start.isoformat(), end.isoformat()),
    )
    return [await hydrate_rental(x) for x in rows]


@api.get("/alquileres/{rid}")
async def rental(rid: str, u=Depends(current)):
    scope, scope_args = await office_scope_sql(u, column="office_id")
    clause = (" AND " + scope) if scope else ""
    r = await sql(
        "SELECT * FROM alquileres WHERE id=?" + clause, (rid, *scope_args), one=True
    )
    if not r or r["estado"] == "confirmando":
        raise HTTPException(404, "Alquiler no encontrado.")
    return await hydrate_rental(r)


@api.post("/alquileres", status_code=201)
async def create_rental(b: AlquilerCreate, u=Depends(roles("Administrador", "Caja"))):
    oid = await office(u, b.office_id, True)
    room = await sql(
        "SELECT office_id FROM ambientes WHERE id=?", (b.ambiente_id,), one=True
    )
    tariff = await sql(
        "SELECT * FROM tarifas_ambientes WHERE id=? AND ambiente_id=?",
        (b.tarifa_id, b.ambiente_id),
        one=True,
    )
    if not room or not tariff or room["office_id"] != oid:
        raise HTTPException(404, "Ambiente o tarifa no encontrados.")
    apply_current_shift(tariff, await room_turnos(b.ambiente_id))
    payer = await sql("SELECT id,nombre,ci,cu FROM clientes WHERE id=?", (b.cliente_id,), one=True)
    if not payer:
        raise HTTPException(400, "El cliente seleccionado no existe.")
    rental_date = parse_iso_date(b.fecha, "La fecha debe tener formato YYYY-MM-DD.")
    schedules = await sql(
        "SELECT dia,CONVERT(varchar(5),desde,108) desde,CONVERT(varchar(5),hasta,108) hasta FROM ambiente_horarios WHERE ambiente_id=?",
        (b.ambiente_id,),
    )
    blocks = day_blocks(schedules, WEEKDAYS[rental_date.weekday()])
    start = normalize_hhmm(b.desde) if b.desde else None
    end = normalize_hhmm(b.hasta) if b.hasta else None
    tariff_start = (
        normalize_hhmm(tariff["desde"]) if tariff.get("desde") is not None else None
    )
    tariff_end = (
        normalize_hhmm(tariff["hasta"]) if tariff.get("hasta") is not None else None
    )
    if start and end and minutes(start) >= minutes(end):
        raise HTTPException(400, "La hora de fin debe ser posterior al inicio.")
    quantity = Decimal(1)
    if tariff["modalidad"] in ("hora", "actividad"):
        if not start or not end:
            raise HTTPException(400, "Indique las horas de inicio y fin.")
        quantity = (
            (Decimal(minutes(end) - minutes(start)) / Decimal(60))
            if tariff["modalidad"] == "hora"
            else Decimal(1)
        )
        if not covered(blocks, start, end):
            raise HTTPException(
                400, "El horario solicitado no está cubierto por un bloque disponible."
            )
    elif tariff["modalidad"] in SHIFT_MODALITIES and (
        start is not None
        and start != tariff_start
        or end is not None
        and end != tariff_end
    ):
        raise HTTPException(400, "El horario debe coincidir con la tarifa.")
    elif tariff["modalidad"] in SHIFT_MODALITIES:
        if not covered(blocks, tariff_start, tariff_end):
            raise HTTPException(
                400, "La tarifa no está cubierta por el horario disponible."
            )
        start, end = tariff_start, tariff_end
    elif tariff["modalidad"] == "dia" and (b.desde or b.hasta):
        raise HTTPException(400, "La modalidad día no admite horas.")
    elif tariff["modalidad"] == "dia":
        if not blocks:
            raise HTTPException(400, "El ambiente no tiene horario disponible ese día.")
    tramos = (
        [{"desde": start, "hasta": end}]
        if tariff["modalidad"] != "dia"
        else blocks
    )
    total = (Decimal(str(tariff["monto"])) * quantity).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    ident = None
    estado = "confirmando"
    gestion = rental_date.year

    # The room/date application lock and serializable transaction are mandatory: see Tablas.Sql.
    def reserve():
        nonlocal ident
        with _connect() as cn:
            c = cn.cursor()
            acquire_app_lock(c, f"room-config:{b.ambiente_id}")
            acquire_app_lock(c, f"room:{b.ambiente_id}:{b.fecha}")
            if tariff["modalidad"] in SHIFT_MODALITIES:
                c.execute(
                    "SELECT CONVERT(varchar(5),desde,108) desde,CONVERT(varchar(5),hasta,108) hasta FROM ambiente_turnos WHERE ambiente_id=? AND turno=?",
                    (b.ambiente_id, tariff["modalidad"]),
                )
                current_shift = _rows(c)
                if current_shift and (
                    current_shift[0]["desde"], current_shift[0]["hasta"]
                ) != (tariff_start, tariff_end):
                    raise HTTPException(
                        409,
                        "El horario del turno cambió; actualice la tarifa y vuelva a intentar.",
                    )
                if not current_shift:
                    c.execute(
                        "SELECT TOP 1 turno FROM ambiente_turnos WHERE ambiente_id=?",
                        (b.ambiente_id,),
                    )
                    if c.fetchone():
                        raise HTTPException(
                            409,
                            "El turno ya no está configurado; actualice la tarifa y vuelva a intentar.",
                        )
            c.execute(
                "SELECT dia,CONVERT(varchar(5),desde,108) desde,CONVERT(varchar(5),hasta,108) hasta FROM ambiente_horarios WHERE ambiente_id=?",
                (b.ambiente_id,),
            )
            fresh_blocks = day_blocks(_rows(c), WEEKDAYS[rental_date.weekday()])
            if tariff["modalidad"] == "dia":
                if not fresh_blocks:
                    raise HTTPException(
                        400, "El ambiente no tiene horario disponible ese día."
                    )
                tramos[:] = fresh_blocks
            elif any(not covered(fresh_blocks, x["desde"], x["hasta"]) for x in tramos):
                raise HTTPException(
                    400,
                    "El horario solicitado no está cubierto por un bloque disponible.",
                )
            c.execute(
                "INSERT INTO alquileres(office_id,ambiente_id,tarifa_id,fecha,cliente_id,cliente_nombre,cliente_ci,cliente_cu,estado,total,cantidad,monto,gestion,confirmation_started_at) OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,SYSUTCDATETIME())",
                (
                    oid,
                    b.ambiente_id,
                    b.tarifa_id,
                    b.fecha,
                    b.cliente_id,
                    payer["nombre"],
                    payer["ci"],
                    payer.get("cu"),
                    estado,
                    total,
                    quantity,
                    tariff["monto"],
                    gestion,
                ),
            )
            ident = c.fetchone()[0]
            c.execute(
                "INSERT INTO ambiente_ocupacion(ambiente_id,fecha) SELECT ?,? WHERE NOT EXISTS(SELECT 1 FROM ambiente_ocupacion WHERE ambiente_id=? AND fecha=?)",
                (b.ambiente_id, b.fecha, b.ambiente_id, b.fecha),
            )
            for tramo in tramos:
                start, end = tramo["desde"], tramo["hasta"]
                c.execute(
                    "SELECT id FROM ocupacion_intervalos WITH (UPDLOCK,HOLDLOCK) WHERE ambiente_id=? AND fecha=? AND desde<? AND hasta>?",
                    (b.ambiente_id, b.fecha, end, start),
                )
                if c.fetchone():
                    raise HTTPException(409, "El horario solicitado ya está reservado.")
                c.execute(
                    "INSERT INTO ocupacion_intervalos(ambiente_id,fecha,alquiler_id,desde,hasta) VALUES(?,?,?,?,?)",
                    (b.ambiente_id, b.fecha, ident, start, end),
                )
                c.execute(
                    "INSERT INTO alquiler_intervalos(alquiler_id,desde,hasta) VALUES(?,?,?)",
                    (ident, start, end),
                )
            c.execute(
                "UPDATE alquileres SET estado=N'reservado',confirmation_started_at=NULL WHERE id=? AND estado=N'confirmando'",
                (ident,),
            )
            cn.commit()

    try:
        await tx(reserve)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            500,
            f"No se pudo verificar la confirmación. Consulte la reserva {ident} antes de reintentar."
            if ident else "No se pudo crear la reserva; vuelva a consultar la disponibilidad.",
        ) from exc
    result = await hydrate_rental(
        await sql("SELECT * FROM alquileres WHERE id=?", (ident,), one=True)
    )
    if b.cobrar_ahora:
        try:
            return await pay_rental(ident, u)
        except HTTPException as exc:
            raise HTTPException(
                exc.status_code, f"{exc.detail} Reserva guardada: {ident}."
            )
    return result


@api.post("/alquileres/{rid}/pagar")
async def pay_rental(rid: str, u=Depends(roles("Administrador", "Caja"))):
    scope, scope_args = await office_scope_sql(u, column="office_id")

    def pay():
        with _connect() as cn:
            c = cn.cursor()
            clause = (" AND " + scope) if scope else ""
            c.execute(
                "SELECT office_id,estado FROM alquileres WITH(UPDLOCK,HOLDLOCK) WHERE id=?"
                + clause,
                (rid, *scope_args),
            )
            r = c.fetchone()
            if not r:
                raise HTTPException(404, "Alquiler no encontrado.")
            # Idempotent transition: a repeated request returns the paid row
            # and never allocates a second shared receipt.
            oid, state = r[0], r[1]
            if state == "pagado":
                return
            if state != "reservado":
                raise HTTPException(400, "Solo se puede pagar un alquiler reservado.")
            year = datetime.now(timezone.utc).year
            code, prefix = allocate_receipt(c, oid, year, "alquiler", rid)
            c.execute(
                "UPDATE alquileres SET estado=N'pagado',gestion=?,cod_comprobante=?,prefijo_comprobante=?,paid_by=?,fecha_pago=SYSUTCDATETIME() WHERE id=? AND estado=N'reservado'",
                (year, code, prefix, u["id"], rid),
            )
            if not c.rowcount:
                raise HTTPException(
                    409, "El alquiler cambió de estado; vuelva a consultarlo."
                )
            cn.commit()

    await tx(pay)
    row = await sql(
        "SELECT * FROM alquileres WHERE id=?" + ((" AND " + scope) if scope else ""),
        (rid, *scope_args),
        one=True,
    )
    return await hydrate_rental(row)


@api.post("/alquileres/{rid}/cancelar")
async def cancel_rental(rid: str, u=Depends(roles("Administrador", "Caja"))):
    scope, scope_args = await office_scope_sql(u, column="office_id")

    def cancel():
        with _connect() as cn:
            c = cn.cursor()
            clause = (" AND " + scope) if scope else ""
            c.execute(
                "SELECT estado FROM alquileres WITH(UPDLOCK,HOLDLOCK) WHERE id=?"
                + clause,
                (rid, *scope_args),
            )
            row = c.fetchone()
            if not row:
                raise HTTPException(404, "Alquiler no encontrado.")
            if row[0] != "cancelado":
                if row[0] != "reservado":
                    raise HTTPException(
                        400, "Solo se puede cancelar un alquiler reservado."
                    )
                c.execute(
                    "UPDATE alquileres SET estado=N'cancelado' WHERE id=? AND estado=N'reservado'",
                    (rid,),
                )
                if not c.rowcount:
                    raise HTTPException(
                        409, "El alquiler cambió de estado; vuelva a consultarlo."
                    )
            # Idempotent cleanup repairs any interval claims left by an earlier attempt.
            c.execute("DELETE FROM ocupacion_intervalos WHERE alquiler_id=?", (rid,))
            cn.commit()

    await tx(cancel)
    row = await sql(
        "SELECT * FROM alquileres WHERE id=?" + ((" AND " + scope) if scope else ""),
        (rid, *scope_args),
        one=True,
    )
    return await hydrate_rental(row)


@api.post("/alquileres/{rid}/anular")
async def void_rental_receipt(rid: str, u=Depends(roles("Administrador", "Caja"))):
    scope, scope_args = await office_scope_sql(u, column="office_id")

    def void():
        with _connect() as cn:
            c = cn.cursor()
            clause = (" AND " + scope) if scope else ""
            c.execute(
                "SELECT ambiente_id,fecha,estado,cod_comprobante,paid_by,fecha_pago "
                "FROM alquileres WITH(UPDLOCK,HOLDLOCK) WHERE id=?" + clause,
                (rid, *scope_args),
            )
            row = c.fetchone()
            if not row:
                raise HTTPException(404, "Alquiler no encontrado.")
            ambiente_id, rental_date, state, code, paid_by, paid_at = row
            if not code or state not in ("pagado", "cancelado"):
                raise HTTPException(
                    400, "Solo se puede anular un comprobante de alquiler pagado."
                )
            if u["rol"] == "Caja":
                if paid_by != u["id"]:
                    raise HTTPException(
                        403, "Caja solo puede anular sus propios comprobantes."
                    )
                if _printed_payment_date(paid_at) != _current_bolivia_date():
                    raise HTTPException(
                        403,
                        "Caja solo puede anular sus comprobantes el día de la fecha impresa.",
                    )

            acquire_app_lock(c, f"room:{ambiente_id}:{rental_date}")
            if state != "cancelado":
                c.execute(
                    "UPDATE alquileres SET estado=N'cancelado' "
                    "WHERE id=? AND estado=N'pagado' AND cod_comprobante=?",
                    (rid, code),
                )
                if not c.rowcount:
                    raise HTTPException(
                        409, "El comprobante cambió de estado; vuelva a consultarlo."
                    )
            c.execute("DELETE FROM ocupacion_intervalos WHERE alquiler_id=?", (rid,))
            cn.commit()

    await tx(void)
    row = await sql(
        "SELECT * FROM alquileres WHERE id=?" + ((" AND " + scope) if scope else ""),
        (rid, *scope_args),
        one=True,
    )
    return await hydrate_rental(row)


def parse_iso_date(value, label="Fecha inválida. Use YYYY-MM-DD."):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        raise HTTPException(400, label)


def _current_bolivia_date() -> date:
    return datetime.now(BOLIVIA_TIMEZONE).date()


def _printed_payment_date(value) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
        if not match:
            return None
        try:
            day, month, year = (int(part) for part in match.groups())
            return date(year, month, day)
        except ValueError:
            return None


@api.get("/pagos/preview-comprobante")
async def preview(
    office_id: Optional[str] = None, u=Depends(roles("Administrador", "Caja"))
):
    oid = await office(u, office_id, True)
    year = datetime.now(timezone.utc).year
    row = await sql(
        "SELECT siguiente FROM comprobante_contadores WHERE office_id=? AND gestion=?",
        (oid, year),
        one=True,
    )
    code = f"{(row['siguiente'] if row else 1):05d}"
    o = await sql(
        "SELECT prefijo_comprobante FROM oficinas WHERE id=?", (oid,), one=True
    )
    return {
        "cod_comprobante": code,
        "gestion": year,
        "prefijo_comprobante": o["prefijo_comprobante"],
        "office_id": oid,
        "display": f"{o['prefijo_comprobante']}-{code} / {year}",
    }


@api.post("/pagos", status_code=201)
async def create_payment(b: PagoCreate, u=Depends(roles("Administrador", "Caja"))):
    oid = await office(u, b.office_id, True)
    year = datetime.now(timezone.utc).year
    payment_date = parse_iso_date(b.fecha_pago).isoformat()
    if b.id_tipo_pago and b.cantidad is None:
        raise HTTPException(400, "Indique la cantidad del concepto.")

    def create():
        with _connect() as cn:
            c = cn.cursor()
            c.execute(
                "SELECT id FROM clientes WHERE id=?",
                (b.cliente_id,),
            )
            if not c.fetchone():
                raise HTTPException(400, "Cliente no encontrado en esta oficina.")
            item = None
            if b.id_tipo_pago:
                c.execute(
                    """SELECT nombre,monto,codigo,id_clasificador
                       FROM tipos_pagos WHERE id=? AND office_id=?""",
                    (b.id_tipo_pago, oid),
                )
                t = c.fetchone()
                if not t:
                    raise HTTPException(
                        400, "Concepto no encontrado en esta oficina."
                    )
                if not t[2] or not t[3]:
                    raise HTTPException(
                        400,
                        "El concepto debe tener código y clasificador presupuestario antes de cobrarlo.",
                    )
                c.execute(
                    "SELECT activa FROM clasificadores_presupuestarios WHERE id=?",
                    (t[3],),
                )
                classifier = c.fetchone()
                if not classifier or not classifier[0]:
                    raise HTTPException(
                        400, "El clasificador presupuestario del concepto está inactivo."
                    )
                qty = Decimal(str(b.cantidad))
                amount = Decimal(str(t[1]))
                line_total = (amount * qty).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                item = (
                    b.id_tipo_pago,
                    t[0],
                    qty,
                    amount,
                    line_total,
                )
            state = "emitido" if item else "borrador"
            unit = item[3] if item else Decimal(0)
            total = item[4] if item else Decimal(0)
            type_id = item[0] if item else None
            quantity = item[2] if item else None
            c.execute(
                """INSERT INTO pagos(office_id,cliente_id,fecha_pago,gestion,
                         estado,monto,total,id_tipo_pago,cantidad,created_by)
                         OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    oid,
                    b.cliente_id,
                    payment_date,
                    year,
                    state,
                    unit,
                    total,
                    type_id,
                    quantity,
                    u["id"],
                ),
            )
            ident = c.fetchone()[0]
            code, prefix = allocate_receipt(c, oid, year, "pago", ident)
            c.execute(
                "UPDATE pagos SET cod_comprobante=?,prefijo_comprobante=? WHERE id=?",
                (code, prefix, ident),
            )
            if item:
                c.execute(
                    """INSERT INTO pago_items(pago_id,id_tipo_pago,tipo_pago_nombre,cantidad,monto,total)
                             VALUES(?,?,?,?,?,?)""",
                    (ident, *item),
                )
            cn.commit()
            return ident

    ident = await tx(create)
    return await hydrate_payment(
        await sql("SELECT * FROM pagos WHERE id=?", (ident,), one=True)
    )


@api.post("/pagos/{pid}/items")
async def add_item(
    pid: str, b: PagoItemCreate, u=Depends(roles("Administrador", "Caja"))
):
    scope, scope_args = await office_scope_sql(u, column="p.office_id")
    qty = Decimal(str(b.cantidad))

    def add():
        with _connect() as cn:
            c = cn.cursor()
            clause = (" AND " + scope) if scope else ""
            c.execute(
                "SELECT p.office_id,p.estado,p.anulado,p.total FROM pagos p WITH(UPDLOCK,HOLDLOCK) WHERE p.id=?"
                + clause,
                (pid, *scope_args),
            )
            p = c.fetchone()
            if not p:
                raise HTTPException(404, "Comprobante no encontrado.")
            if p[2] or p[1] != "borrador":
                raise HTTPException(
                    400,
                    "Solo se pueden adicionar conceptos a un comprobante en borrador.",
                )
            c.execute(
                """SELECT nombre,monto,codigo,id_clasificador
                   FROM tipos_pagos WHERE id=? AND office_id=?""",
                (b.id_tipo_pago, p[0]),
            )
            t = c.fetchone()
            if not t:
                raise HTTPException(400, "Concepto no encontrado en esta oficina.")
            if not t[2] or not t[3]:
                raise HTTPException(
                    400,
                    "El concepto debe tener código y clasificador presupuestario antes de cobrarlo.",
                )
            c.execute(
                "SELECT activa FROM clasificadores_presupuestarios WHERE id=?",
                (t[3],),
            )
            classifier = c.fetchone()
            if not classifier or not classifier[0]:
                raise HTTPException(
                    400, "El clasificador presupuestario del concepto está inactivo."
                )
            amount = Decimal(str(t[1]))
            line_total = (amount * qty).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            c.execute("SELECT COUNT(*) FROM pago_items WHERE pago_id=?", (pid,))
            old_count = c.fetchone()[0]
            c.execute(
                "INSERT INTO pago_items(pago_id,id_tipo_pago,tipo_pago_nombre,cantidad,monto,total) VALUES(?,?,?,?,?,?)",
                (pid, b.id_tipo_pago, t[0], qty, amount, line_total),
            )
            new_total = Decimal(str(p[3] or 0)) + line_total
            if old_count == 0:
                c.execute(
                    "UPDATE pagos SET total=?,monto=?,id_tipo_pago=?,cantidad=?,edited_at=SYSUTCDATETIME(),edited_by=? WHERE id=?",
                    (new_total, amount, b.id_tipo_pago, qty, u["id"], pid),
                )
            else:
                c.execute(
                    "UPDATE pagos SET total=?,monto=0,id_tipo_pago=NULL,cantidad=NULL,edited_at=SYSUTCDATETIME(),edited_by=? WHERE id=?",
                    (new_total, u["id"], pid),
                )
            cn.commit()

    await tx(add)
    return await hydrate_payment(
        await sql("SELECT * FROM pagos WHERE id=?", (pid,), one=True)
    )


@api.post("/pagos/{pid}/finalizar")
async def finalize_payment(pid: str, u=Depends(roles("Administrador", "Caja"))):
    scope, scope_args = await office_scope_sql(u, column="p.office_id")

    def finish():
        with _connect() as cn:
            c = cn.cursor()
            clause = (" AND " + scope) if scope else ""
            c.execute(
                "SELECT p.office_id,p.estado,p.anulado FROM pagos p WITH(UPDLOCK,HOLDLOCK) WHERE p.id=?"
                + clause,
                (pid, *scope_args),
            )
            p = c.fetchone()
            if not p:
                raise HTTPException(404, "Comprobante no encontrado.")
            if p[2]:
                raise HTTPException(400, "El comprobante está anulado.")
            if p[1] != "borrador":
                raise HTTPException(400, "El comprobante ya fue emitido.")
            c.execute("SELECT COUNT(*) FROM pago_items WHERE pago_id=?", (pid,))
            if not c.fetchone()[0]:
                raise HTTPException(
                    400, "Agregue al menos un concepto antes de emitir el comprobante."
                )
            c.execute(
                "UPDATE pagos SET estado=N'emitido',edited_at=SYSUTCDATETIME(),edited_by=? WHERE id=?",
                (u["id"], pid),
            )
            cn.commit()

    await tx(finish)
    return await hydrate_payment(
        await sql("SELECT * FROM pagos WHERE id=?", (pid,), one=True)
    )


@api.delete("/pagos/{pid}/borrador")
async def delete_draft(pid: str, u=Depends(roles("Administrador", "Caja"))):
    scope, scope_args = await office_scope_sql(u, column="p.office_id")

    def discard():
        with _connect() as cn:
            c = cn.cursor()
            clause = (" AND " + scope) if scope else ""
            c.execute(
                "SELECT p.office_id,p.gestion,p.cod_comprobante FROM pagos p WITH(UPDLOCK,HOLDLOCK) WHERE p.id=? AND p.estado=N'borrador'"
                + clause,
                (pid, *scope_args),
            )
            p = c.fetchone()
            if not p:
                raise HTTPException(404, "Comprobante no encontrado.")
            reused = False
            acquire_app_lock(c, f"receipt:{p[0]}:{p[1]}")
            c.execute(
                "SELECT siguiente FROM comprobante_contadores WITH(UPDLOCK,HOLDLOCK) WHERE office_id=? AND gestion=?",
                (p[0], p[1]),
            )
            n = c.fetchone()
            try:
                draft_seq = int(p[2]) if p[2] else 0
            except (TypeError, ValueError):
                draft_seq = 0
            if n and draft_seq > 0 and draft_seq == n[0] - 1:
                c.execute(
                    "UPDATE comprobante_contadores SET siguiente=siguiente-1 WHERE office_id=? AND gestion=? AND siguiente=?",
                    (p[0], p[1], n[0]),
                )
                reused = c.rowcount == 1
            if reused:
                c.execute(
                    "DELETE FROM comprobante_asignaciones WHERE office_id=? AND gestion=? AND codigo=?",
                    (p[0], p[1], p[2]),
                )
            c.execute("DELETE FROM pago_items WHERE pago_id=?", (pid,))
            c.execute("DELETE FROM pagos WHERE id=?", (pid,))
            cn.commit()
            return reused

    return {"ok": True, "correlativo_reutilizado": await tx(discard)}


@api.get("/pagos/{pid}")
async def get_payment(pid: str, u=Depends(current)):
    scope, scope_args = await office_scope_sql(u, column="p.office_id")
    clause = (" AND " + scope) if scope else ""
    row = await sql(
        "SELECT p.* FROM pagos p WHERE p.id=?" + clause, (pid, *scope_args), one=True
    )
    if not row:
        raise HTTPException(404, "Comprobante no encontrado.")
    return await hydrate_payment(row)


@api.get("/pagos")
async def payments(
    pag: int = Query(1, ge=1),
    tam: int = Query(20, ge=1, le=100),
    q: Optional[str] = None,
    id_tipo_pago: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    incluir_anulados: bool = True,
    created_by: Optional[str] = None,
    office_id: Optional[str] = None,
    u=Depends(current),
):
    if fecha_desde:
        parse_iso_date(fecha_desde)
    if fecha_hasta:
        parse_iso_date(fecha_hasta)
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(
            400, "La fecha inicial no puede ser posterior a la fecha final."
        )
    scope, scope_args = await office_scope_sql(u, office_id, "p.office_id")
    clauses = ["p.estado<>N'borrador'"]
    args = []
    if scope:
        clauses.append(scope)
        args.extend(scope_args)
    if not incluir_anulados:
        clauses.append("p.anulado=0")
    if created_by:
        clauses.append("p.created_by=?")
        args.append(created_by)
    if fecha_desde:
        clauses.append("p.fecha_pago>=?")
        args.append(fecha_desde)
    if fecha_hasta:
        clauses.append("p.fecha_pago<=?")
        args.append(fecha_hasta)
    if id_tipo_pago:
        clauses.append(
            "(p.id_tipo_pago=? OR EXISTS(SELECT 1 FROM pago_items pi WHERE pi.pago_id=p.id AND pi.id_tipo_pago=?))"
        )
        args.extend([id_tipo_pago, id_tipo_pago])
    term = (q or "").strip()
    if term:
        receipt = re.fullmatch(
            r"(?:(?P<prefix>[A-Za-z]{3})[ ]*-[ ]*)?(?P<code>[0-9]{1,5})(?:[ ]*/[ ]*(?P<year>[0-9]{4}))?",
            term,
        )
        if receipt:
            parts = ["p.cod_comprobante=?"]
            args.append(receipt["code"].zfill(5))
            if receipt["year"]:
                parts.append("p.gestion=?")
                args.append(int(receipt["year"]))
            if receipt["prefix"]:
                parts.append("UPPER(p.prefijo_comprobante)=?")
                args.append(receipt["prefix"].upper())
            clauses.append("(" + " AND ".join(parts) + ")")
        else:
            like = "%" + term + "%"
            clauses.append(
                """(p.cod_comprobante LIKE ? OR EXISTS(
                SELECT 1 FROM clientes s WHERE s.id=p.cliente_id
                AND (s.nombre LIKE ? OR s.ci LIKE ? OR s.cu LIKE ?))
                OR EXISTS(SELECT 1 FROM pago_items pi JOIN tipos_pagos t ON t.id=pi.id_tipo_pago
                WHERE pi.pago_id=p.id AND (t.nombre LIKE ? OR pi.tipo_pago_nombre LIKE ?)))"""
            )
            args.extend([like] * 6)
    where = " AND ".join(clauses)
    total = (
        await sql("SELECT COUNT(*) n FROM pagos p WHERE " + where, args, one=True)
    )["n"]
    rows = await sql(
        "SELECT p.* FROM pagos p WHERE "
        + where
        + " ORDER BY p.created_at DESC,p.id OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        args + [(pag - 1) * tam, tam],
    )
    return page([await hydrate_payment(x) for x in rows], total, pag, tam)


@api.put("/pagos/{pid}")
async def update_payment(
    pid: str, b: PagoCreate, u=Depends(roles("Administrador", "Caja"))
):
    scope, scope_args = await office_scope_sql(u, column="p.office_id")
    payment_date = parse_iso_date(b.fecha_pago).isoformat()

    def update():
        with _connect() as cn:
            c = cn.cursor()
            clause = (" AND " + scope) if scope else ""
            c.execute(
                "SELECT p.office_id,p.cliente_id,p.fecha_pago,p.id_tipo_pago,p.cantidad,p.monto,p.total,p.estado,p.anulado FROM pagos p WITH(UPDLOCK,HOLDLOCK) WHERE p.id=?"
                + clause,
                (pid, *scope_args),
            )
            p = c.fetchone()
            if not p:
                raise HTTPException(404, "Pago no encontrado.")
            if p[8]:
                raise HTTPException(400, "No se puede editar un pago anulado.")
            if p[7] == "borrador":
                raise HTTPException(
                    400, "No se puede editar un borrador desde esta pantalla."
                )
            c.execute(
                "SELECT id,id_tipo_pago,cantidad,monto,total FROM pago_items WHERE pago_id=? ORDER BY id",
                (pid,),
            )
            items = c.fetchall()
            if len(items) > 1:
                raise HTTPException(
                    400,
                    "No se puede editar desde esta pantalla un comprobante con varios conceptos.",
                )
            if b.office_id and b.office_id != p[0]:
                raise HTTPException(400, "No se puede cambiar la oficina de un pago.")
            sets = []
            values = []
            if b.cliente_id and b.cliente_id != p[1]:
                c.execute(
                    "SELECT id FROM clientes WHERE id=?",
                    (b.cliente_id,),
                )
                if not c.fetchone():
                    raise HTTPException(
                        400, "Cliente no encontrado en esta oficina."
                    )
                sets.append("cliente_id=?")
                values.append(b.cliente_id)
            item = items[0] if items else None
            type_id = item[1] if item else p[3]
            quantity = Decimal(str(item[2] if item else (p[4] or 0)))
            amount = Decimal(str(item[3] if item else (p[5] or 0)))
            if b.id_tipo_pago and b.id_tipo_pago != type_id:
                c.execute(
                    """SELECT nombre,monto,codigo,id_clasificador
                       FROM tipos_pagos WHERE id=? AND office_id=?""",
                    (b.id_tipo_pago, p[0]),
                )
                tp = c.fetchone()
                if not tp:
                    raise HTTPException(
                        400, "Concepto no encontrado en esta oficina."
                    )
                if not tp[2] or not tp[3]:
                    raise HTTPException(
                        400,
                        "El concepto debe tener código y clasificador presupuestario antes de cobrarlo.",
                    )
                c.execute(
                    "SELECT activa FROM clasificadores_presupuestarios WHERE id=?",
                    (tp[3],),
                )
                classifier = c.fetchone()
                if not classifier or not classifier[0]:
                    raise HTTPException(
                        400, "El clasificador presupuestario del concepto está inactivo."
                    )
                type_id = b.id_tipo_pago
                amount = Decimal(str(tp[1]))
                sets.extend(["id_tipo_pago=?", "monto=?"])
                values.extend([type_id, amount])
                if item:
                    c.execute(
                        "UPDATE pago_items SET id_tipo_pago=?,tipo_pago_nombre=?,monto=? WHERE id=?",
                        (type_id, tp[0], amount, item[0]),
                    )
            if b.cantidad is not None and Decimal(str(b.cantidad)) != quantity:
                quantity = Decimal(str(b.cantidad))
                sets.extend(["cantidad=?"])
                values.append(quantity)
                if item:
                    c.execute(
                        "UPDATE pago_items SET cantidad=? WHERE id=?",
                        (quantity, item[0]),
                    )
            total = (
                (amount * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if (item or type_id)
                else Decimal(str(p[6] or 0))
            )
            if (item or type_id) and (
                b.cantidad is not None or (b.id_tipo_pago and b.id_tipo_pago != p[3])
            ):
                sets.append("total=?")
                values.append(total)
                if item:
                    c.execute(
                        "UPDATE pago_items SET total=? WHERE id=?", (total, item[0])
                    )
            if payment_date != str(p[2]):
                sets.append("fecha_pago=?")
                values.append(payment_date)
            if not sets:
                raise HTTPException(400, "Sin cambios.")
            sets.extend(["edited_at=SYSUTCDATETIME()", "edited_by=?"])
            values.extend([u["id"], pid])
            c.execute("UPDATE pagos SET " + ",".join(sets) + " WHERE id=?", values)
            cn.commit()

    await tx(update)
    return await hydrate_payment(
        await sql("SELECT * FROM pagos WHERE id=?", (pid,), one=True)
    )


@api.post("/pagos/{pid}/anular")
async def void_payment(pid: str, u=Depends(roles("Administrador", "Caja"))):
    scope, scope_args = await office_scope_sql(u, column="p.office_id")

    def void():
        with _connect() as cn:
            c = cn.cursor()
            clause = (" AND " + scope) if scope else ""
            c.execute(
                "SELECT p.anulado,p.fecha_pago,p.created_by FROM pagos p WITH(UPDLOCK,HOLDLOCK) WHERE p.id=?"
                + clause,
                (pid, *scope_args),
            )
            row = c.fetchone()
            if not row:
                raise HTTPException(404, "Pago no encontrado.")
            if row[0]:
                raise HTTPException(400, "El pago ya está anulado.")
            if u["rol"] == "Caja":
                if row[2] != u["id"]:
                    raise HTTPException(
                        403, "Caja solo puede anular sus propios comprobantes."
                    )
                if _printed_payment_date(row[1]) != _current_bolivia_date():
                    raise HTTPException(
                        403,
                        "Caja solo puede anular sus comprobantes el día de la fecha impresa.",
                    )
            c.execute(
                "UPDATE pagos SET anulado=1,anulado_at=SYSUTCDATETIME(),anulado_by=? WHERE id=? AND anulado=0",
                (u["id"], pid),
            )
            if not c.rowcount:
                raise HTTPException(
                    409, "El pago cambió de estado; vuelva a consultarlo."
                )
            cn.commit()

    await tx(void)
    return {"ok": True}


@api.get("/comprobantes")
async def receipts(
    q: Optional[str] = None,
    id_tipo_pago: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    created_by: Optional[str] = None,
    office_id: Optional[str] = None,
    pag: int = Query(1, ge=1),
    tam: int = Query(20, ge=1, le=100),
    u=Depends(current),
):
    if fecha_desde:
        parse_iso_date(fecha_desde)
    if fecha_hasta:
        parse_iso_date(fecha_hasta)
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(
            400, "La fecha inicial no puede ser posterior a la fecha final."
        )
    ps, pa = await office_scope_sql(u, office_id, "p.office_id")
    rs, ra = await office_scope_sql(u, office_id, "a.office_id")
    pc = []
    pv = []
    rc = []
    rv = []
    if ps:
        pc.append(ps)
        pv.extend(pa)
    if rs:
        rc.append(rs)
        rv.extend(ra)
    pc.append("p.estado<>N'borrador'")
    rc.append(
        "(a.estado=N'pagado' OR "
        "(a.estado=N'cancelado' AND a.cod_comprobante IS NOT NULL AND a.cod_comprobante<>N''))"
    )
    if fecha_desde:
        pc.append("p.fecha_pago>=?")
        pv.append(fecha_desde)
        rc.append("a.fecha_pago>=?")
        rv.append(fecha_desde)
    if fecha_hasta:
        pc.append("p.fecha_pago<=?")
        pv.append(fecha_hasta)
        rc.append("a.fecha_pago<DATEADD(day,1,?)")
        rv.append(fecha_hasta)
    if created_by:
        pc.append("p.created_by=?")
        pv.append(created_by)
        rc.append("a.paid_by=?")
        rv.append(created_by)
    if id_tipo_pago:
        pc.append(
            "(p.id_tipo_pago=? OR EXISTS(SELECT 1 FROM pago_items i WHERE i.pago_id=p.id AND i.id_tipo_pago=?))"
        )
        pv.extend([id_tipo_pago, id_tipo_pago])
        rc.append("1=0")
    term = (q or "").strip()
    if term:
        receipt = re.fullmatch(
            r"(?:(?P<prefix>[A-Za-z]{3})[ ]*-[ ]*)?(?P<code>[0-9]{1,5})(?:[ ]*/[ ]*(?P<year>[0-9]{4}))?",
            term,
        )
        if receipt:
            for clauses, values, alias in ((pc, pv, "p"), (rc, rv, "a")):
                checks = [f"{alias}.cod_comprobante=?"]
                values.append(receipt["code"].zfill(5))
                if receipt["year"]:
                    checks.append(f"{alias}.gestion=?")
                    values.append(int(receipt["year"]))
                if receipt["prefix"]:
                    checks.append(f"UPPER({alias}.prefijo_comprobante)=?")
                    values.append(receipt["prefix"].upper())
                clauses.append("(" + " AND ".join(checks) + ")")
        else:
            like = "%" + term + "%"
            pc.append(
                """(p.cod_comprobante LIKE ? OR EXISTS(SELECT 1 FROM clientes s WHERE s.id=p.cliente_id AND (s.nombre LIKE ? OR s.ci LIKE ? OR s.cu LIKE ?))
                       OR EXISTS(SELECT 1 FROM pago_items i JOIN tipos_pagos t ON t.id=i.id_tipo_pago WHERE i.pago_id=p.id AND (t.nombre LIKE ? OR i.tipo_pago_nombre LIKE ?)))"""
            )
            pv.extend([like] * 6)
            rc.append(
                """(a.cod_comprobante LIKE ? OR a.cliente_nombre LIKE ? OR a.cliente_ci LIKE ? OR a.cliente_cu LIKE ?
                       OR EXISTS(SELECT 1 FROM ambientes e WHERE e.id=a.ambiente_id AND e.nombre LIKE ?)
                       OR EXISTS(SELECT 1 FROM tarifas_ambientes t WHERE t.id=a.tarifa_id AND t.nombre LIKE ?))"""
            )
            rv.extend([like] * 6)
    student_rows = await sql("SELECT p.* FROM pagos p WHERE " + " AND ".join(pc), pv)
    rental_rows = await sql(
        "SELECT a.* FROM alquileres a WHERE " + " AND ".join(rc), rv
    )
    merged = []
    for row in student_rows:
        row = await hydrate_payment(row)
        row["origen"] = "pago"
        merged.append(row)
    for row in rental_rows:
        row = await hydrate_rental(row)
        if isinstance(row.get("fecha_pago"), str):
            row["fecha_pago"] = row["fecha_pago"][:10]
        row["origen"] = "alquiler"
        merged.append(row)
    merged.sort(
        key=lambda x: (str(x.get("fecha_pago") or ""), str(x.get("id") or "")),
        reverse=True,
    )
    total = len(merged)
    return page(merged[(pag - 1) * tam : pag * tam], total, pag, tam)


@api.get("/reportes")
async def reports(
    periodo: Literal["diario", "semanal", "mensual", "rango"] = "diario",
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    created_by: Optional[str] = None,
    office_id: Optional[str] = None,
    u=Depends(roles("Administrador")),
):
    today = date.today()
    if periodo == "diario":
        start = end = today
    elif periodo == "semanal":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif periodo == "mensual":
        start = today.replace(day=1)
        next_month = (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )
        end = next_month - timedelta(days=1)
    else:
        if not desde or not hasta:
            raise HTTPException(400, "Se requieren fechas desde y hasta")
        start = parse_iso_date(desde)
        end = parse_iso_date(hasta)
    if periodo == "rango" and (desde is None or hasta is None):
        raise HTTPException(400, "Se requieren fechas desde y hasta")
    if end < start:
        raise HTTPException(
            400, "La fecha inicial no puede ser posterior a la fecha final."
        )
    d, h = start.isoformat(), end.isoformat()
    scope, scope_args = await office_scope_sql(u, office_id, "p.office_id")
    pc = ["p.estado<>N'borrador'", "p.fecha_pago>=?", "p.fecha_pago<=?"]
    pv = [d, h]
    if scope:
        pc.append(scope)
        pv.extend(scope_args)
    if created_by:
        pc.append("p.created_by=?")
        pv.append(created_by)
    pagos = await sql(
        "SELECT p.* FROM pagos p WHERE "
        + " AND ".join(pc)
        + " ORDER BY p.fecha_pago,p.id",
        pv,
    )
    rs, rv = await office_scope_sql(u, office_id, "a.office_id")
    rc = ["a.estado=N'pagado'", "a.fecha_pago>=?", "a.fecha_pago<DATEADD(day,1,?)"]
    ra = [d, h]
    if rs:
        rc.append(rs)
        ra.extend(rv)
    if created_by:
        rc.append("a.paid_by=?")
        ra.append(created_by)
    rentals = await sql(
        "SELECT a.* FROM alquileres a WHERE "
        + " AND ".join(rc)
        + " ORDER BY a.fecha_pago,a.id",
        ra,
    )
    pagos = [await hydrate_payment(p) for p in pagos]
    rentals = [await hydrate_rental(r) for r in rentals]
    valid = [p for p in pagos if not p["anulado"]]
    voided = [p for p in pagos if p["anulado"]]
    student = sum(float(p["total"]) for p in valid)
    rent = sum(float(x["total"]) for x in rentals)
    void_total = sum(float(p["total"]) for p in voided)
    office_id_value = None
    office_name = "Todas las oficinas"
    if scope:
        office_id_value = scope_args[0]
        office_row = await sql(
            "SELECT nombre FROM oficinas WHERE id=?", (office_id_value,), one=True
        )
        office_name = (office_row or {}).get("nombre")
    return {
        "desde": d,
        "hasta": h,
        "office_id": office_id_value,
        "office_nombre": office_name,
        "pagos": pagos,
        "alquileres": rentals,
        "totales": {
            "validos": student + rent,
            "pagos": student,
            "alquileres": rent,
            "anulados": void_total,
            "diferencia": student + rent - void_total,
            "count_validos": len(valid) + len(rentals),
            "count_anulados": len(voided),
        },
    }


@api.get("/dashboard/stats")
async def dashboard(office_id: Optional[str] = None, u=Depends(current)):
    scope, args = await office_scope_sql(u, office_id)
    suffix = (" WHERE " + scope) if scope else ""
    day = date.today().isoformat()
    payments_where = (
        " AND " if suffix else " WHERE "
    ) + "fecha_pago=? AND anulado=0 AND estado<>N'borrador'"
    params = args + [day]
    p = await sql(
        "SELECT COUNT(*) n,COALESCE(SUM(total),0) total FROM pagos"
        + suffix
        + payments_where,
        params,
        one=True,
    )
    students = (
        await sql("SELECT COUNT(*) n FROM clientes", (), one=True)
    )["n"]
    types = (await sql("SELECT COUNT(*) n FROM tipos_pagos" + suffix, args, one=True))[
        "n"
    ]
    office_id_value = args[0] if scope else None
    office_row = (
        await sql(
            "SELECT nombre FROM oficinas WHERE id=?", (office_id_value,), one=True
        )
        if office_id_value
        else None
    )
    office_name = (office_row or {}).get("nombre") or "Todas las oficinas"
    return {
        "clientes": students,
        "tipospagos": types,
        "pagos_hoy": p["n"],
        "monto_hoy": float(p["total"]),
        "office_id": office_id_value,
        "office_nombre": office_name,
        "institucion": {
            "linea1": "Universidad Mayor, Real y Pontificia de San Francisco Xavier",
            "linea2": office_name,
            "linea3": "Administración",
        },
    }


@api.get("/")
async def root():
    return {"message": "Comprobantes USFX SQL Server"}





async def reconcile_startup():
    """Validate the separately-run Tablas.Sql schema, repair expired work, and seed
    the configured administrator.  It intentionally never performs DDL."""
    required = (
        "oficinas",
        "usuarios",
        "clientes",
        "clasificadores_presupuestarios",
        "tipos_pagos",
        "ambientes",
        "ambiente_horarios",
        "ambiente_turnos",
        "tarifas_ambientes",
        "pagos",
        "pago_items",
        "alquileres",
        "alquiler_intervalos",
        "ambiente_ocupacion",
        "ocupacion_intervalos",
        "comprobante_contadores",
        "comprobante_asignaciones",
    )
    for table in required:
        exists = await sql("SELECT OBJECT_ID(?,N'U') id", (f"dbo.{table}",), one=True)
        if not exists or not exists.get("id"):
            raise RuntimeError(
                f"Falta la tabla dbo.{table}; ejecute backend/Tablas.Sql."
            )

    def reconcile():
        with _connect() as cn:
            c = cn.cursor()
            c.execute(
                """UPDATE alquileres SET estado=N'cancelado',confirmation_started_at=NULL
                         WHERE estado=N'confirmando'
                         AND (confirmation_started_at IS NULL OR confirmation_started_at<DATEADD(minute,-30,SYSUTCDATETIME()))"""
            )
            c.execute(
                """DELETE i FROM ocupacion_intervalos i LEFT JOIN alquileres a ON a.id=i.alquiler_id
                         WHERE a.id IS NULL OR a.estado=N'cancelado'"""
            )
            c.execute(
                """INSERT INTO ambiente_ocupacion(ambiente_id,fecha)
                         SELECT DISTINCT a.ambiente_id,a.fecha FROM alquileres a
                         JOIN alquiler_intervalos t ON t.alquiler_id=a.id
                         WHERE a.estado<>N'cancelado'
                         AND NOT EXISTS(SELECT 1 FROM ambiente_ocupacion o WHERE o.ambiente_id=a.ambiente_id AND o.fecha=a.fecha)"""
            )
            c.execute(
                """INSERT INTO ocupacion_intervalos(ambiente_id,fecha,alquiler_id,desde,hasta)
                         SELECT a.ambiente_id,a.fecha,a.id,t.desde,t.hasta
                         FROM alquileres a JOIN alquiler_intervalos t ON t.alquiler_id=a.id
                         WHERE a.estado<>N'cancelado'
                         AND NOT EXISTS(SELECT 1 FROM ocupacion_intervalos i
                                        WHERE i.alquiler_id=a.id AND i.desde=t.desde AND i.hasta=t.hasta)"""
            )
            c.execute(
                """SELECT TOP 1 a.ambiente_id,a.fecha FROM ocupacion_intervalos i
                         JOIN alquileres a ON a.id=i.alquiler_id AND a.estado<>N'cancelado'
                         JOIN ocupacion_intervalos j ON j.ambiente_id=i.ambiente_id AND j.fecha=i.fecha
                           AND j.id>i.id AND j.alquiler_id<>i.alquiler_id
                           AND j.desde<i.hasta AND j.hasta>i.desde
                         JOIN alquileres b ON b.id=j.alquiler_id AND b.estado<>N'cancelado'"""
            )
            conflict = c.fetchone()
            if conflict:
                raise RuntimeError(
                    f"Hay alquileres activos superpuestos en {conflict[0]} para {conflict[1]}; resuelva el conflicto antes de iniciar."
                )
            c.execute(
                """UPDATE p SET prefijo_comprobante=o.prefijo_comprobante
                         FROM pagos p JOIN oficinas o ON o.id=p.office_id
                         WHERE p.prefijo_comprobante IS NULL AND p.cod_comprobante IS NOT NULL"""
            )
            c.execute(
                """UPDATE a SET prefijo_comprobante=o.prefijo_comprobante
                         FROM alquileres a JOIN oficinas o ON o.id=a.office_id
                         WHERE a.prefijo_comprobante IS NULL AND a.cod_comprobante IS NOT NULL"""
            )
            c.execute(
                """INSERT INTO comprobante_asignaciones(office_id,gestion,codigo,origen,origen_id)
                         SELECT p.office_id,p.gestion,p.cod_comprobante,N'pago',p.id FROM pagos p
                         WHERE p.cod_comprobante IS NOT NULL
                           AND NOT EXISTS(SELECT 1 FROM comprobante_asignaciones x WHERE x.origen=N'pago' AND x.origen_id=p.id)"""
            )
            c.execute(
                """INSERT INTO comprobante_asignaciones(office_id,gestion,codigo,origen,origen_id)
                         SELECT a.office_id,a.gestion,a.cod_comprobante,N'alquiler',a.id FROM alquileres a
                         WHERE a.estado=N'pagado' AND a.cod_comprobante IS NOT NULL
                           AND NOT EXISTS(SELECT 1 FROM comprobante_asignaciones x WHERE x.origen=N'alquiler' AND x.origen_id=a.id)"""
            )
            c.execute(""";WITH high_water AS (
                           SELECT office_id,gestion,MAX(TRY_CONVERT(bigint,codigo)) max_code
                           FROM comprobante_asignaciones GROUP BY office_id,gestion
                         )
                         UPDATE n SET siguiente=CASE WHEN n.siguiente<=h.max_code THEN h.max_code+1 ELSE n.siguiente END
                         FROM comprobante_contadores n JOIN high_water h ON h.office_id=n.office_id AND h.gestion=n.gestion
                         WHERE h.max_code IS NOT NULL""")
            c.execute(
                """;WITH high_water AS (
                           SELECT office_id,gestion,MAX(TRY_CONVERT(bigint,codigo)) max_code
                           FROM comprobante_asignaciones GROUP BY office_id,gestion
                         )
                         INSERT INTO comprobante_contadores(office_id,gestion,siguiente)
                         SELECT h.office_id,h.gestion,h.max_code+1 FROM high_water h
                         WHERE h.max_code IS NOT NULL AND NOT EXISTS(
                           SELECT 1 FROM comprobante_contadores n WHERE n.office_id=h.office_id AND n.gestion=h.gestion)"""
            )
            cn.commit()

    await tx(reconcile)
    email = os.getenv("ADMIN_EMAIL", SUPER_ADMIN_EMAIL).strip().lower()
    password = os.getenv("ADMIN_PASSWORD")
    name = os.getenv("ADMIN_NAME", "Administrador").strip()
    if not password:
        raise RuntimeError(
            "Falta configurar ADMIN_PASSWORD para inicializar el Super Admin."
        )
    admin = await sql(
        "SELECT * FROM usuarios WHERE email_key=LOWER(LTRIM(RTRIM(?)))",
        (email,),
        one=True,
    )
    if not admin:
        await sql(
            "INSERT INTO usuarios(codigo,email,nombre,rol,password_hash) VALUES(?,?,?,?,?)",
            ("000", email, name, SUPER_ADMIN_ROLE, hashpw(password)),
            write=True,
        )
    else:
        update_password = not verifypw(password, admin["password_hash"])
        await sql(
            """UPDATE usuarios SET nombre=?,rol=?,office_id=NULL,password_hash=?
                     WHERE id=?""",
            (
                name,
                SUPER_ADMIN_ROLE,
                hashpw(password) if update_password else admin["password_hash"],
                admin["id"],
            ),
            write=True,
        )


@app.on_event("startup")
async def startup():
    await reconcile_startup()

cors_origins_raw = os.getenv("CORS_ORIGINS", "*")
origins = cors_origins_raw.split(",") if cors_origins_raw else []


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)



register_client_routes(api, SQLClientes(sql), roles("Administrador", "Caja"), roles("Administrador", "Caja"), roles("SuperAdmin"))
app.include_router(api)
