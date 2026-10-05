import os
import logging
import re
import itertools
import string
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import bcrypt
import jwt
import uuid
from jwt.exceptions import InvalidTokenError
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Query, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator, model_validator
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
from typing import List, Optional, Literal

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


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ----------------------------- CONFIG -----------------------------
# MongoDB connection
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
# JWT Configuration
JWT_SECRET_KEY = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRES_MIN = 60 * 8
# User Enviroment Configuration
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
ADMIN_NAME = os.environ["ADMIN_NAME"]
SUPER_ADMIN_EMAIL = "admin@usfx.bo"
SUPER_ADMIN_ROLE = "SuperAdmin"

# ----------------------------- DB -----------------------------
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ----------------------------- APP -----------------------------
app = FastAPI(
    title="Comprobantes USFX",
    default_response_class=DateFormattedJSONResponse,
)
api = APIRouter(
    prefix="/api",
    default_response_class=DateFormattedJSONResponse,
)
# Security
security = HTTPBearer()

ROLES = ("Administrador", "Caja", "Consultas")
ALL_ROLES = (SUPER_ADMIN_ROLE, *ROLES)


# ----------------------------- MODELS -----------------------------
class UserPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: EmailStr
    nombre: str
    rol: Literal["SuperAdmin", "Administrador", "Caja", "Consultas"]
    office_id: Optional[str] = None
    office_nombre: Optional[str] = None
    created_at: Optional[str] = None


class UserCreate(BaseModel):
    email: EmailStr
    nombre: str
    password: str = Field(min_length=4)
    rol: Literal["Administrador", "Caja", "Consultas"]
    office_id: Optional[str] = None


class UserUpdate(BaseModel):
    nombre: Optional[str] = None
    rol: Optional[Literal["Administrador", "Caja", "Consultas"]] = None
    password: Optional[str] = Field(default=None, min_length=4)
    office_id: Optional[str] = None


class OfficeBase(BaseModel):
    nombre: str
    prefijo_comprobante: str = Field(
        min_length=3, max_length=3, pattern=r"^[A-Z]{3}$"
    )
    suboficina: str = Field(default="", max_length=100)
    activa: bool = True

    @field_validator("prefijo_comprobante", mode="before")
    @classmethod
    def normalize_receipt_prefix(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("suboficina", mode="before")
    @classmethod
    def normalize_suboffice(cls, value):
        return value.strip() if isinstance(value, str) else value


class OfficeCreate(OfficeBase):
    pass


class Office(OfficeBase):
    id: str
    created_at: Optional[str] = None


class OfficePaginationResponse(BaseModel):
    items: List[Office]
    total: int
    page: int
    size: int
    pages: int

class UserPaginationResponse(BaseModel):
    items: List[UserPublic]
    total: int
    page: int
    size: int
    pages: int

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    usuario: UserPublic


class EstudianteBase(BaseModel):
    ci: str
    cu: Optional[str] = ""
    nombre: str
    gestion: int
    office_id: Optional[str] = None
    office_nombre: Optional[str] = None


class EstudianteCreate(EstudianteBase):
    pass


class Estudiante(EstudianteBase):
    id: str    


class PaginacionEstudiantes(BaseModel):
    items: List[Estudiante]
    total: int
    page: int
    size: int
    pages: int


class PersonaBase(BaseModel):
    ci: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=200)

    @field_validator("ci", "nombre", mode="before")
    @classmethod
    def normalize_person_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class PersonaCreate(PersonaBase):
    pass


class Persona(PersonaBase):
    id: str
    created_at: Optional[str] = None


class PaginacionPersonas(BaseModel):
    items: List[Persona]
    total: int
    page: int
    size: int
    pages: int


class TipoPagoBase(BaseModel):
    nombre: str
    monto: float
    descripcion: Optional[str] = ""
    inicio: str  # ISO date YYYY-MM-DD
    fin: Optional[str] = None
    office_id: Optional[str] = None
    office_nombre: Optional[str] = None


class TipoPagoCreate(TipoPagoBase):
    pass


class TipoPago(TipoPagoBase):
    id: str    


class PaginacionTiposPagos(BaseModel):
    items: List[TipoPago]
    total: int
    page: int
    size: int
    pages: int


class BloqueHorarioAmbiente(BaseModel):
    dia: Literal["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    desde: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    hasta: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.desde >= self.hasta:
            raise ValueError("La hora de fin debe ser posterior a la hora de inicio.")
        return self


class AmbienteBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: Optional[str] = Field(default="", max_length=500)
    horarios: List[BloqueHorarioAmbiente] = Field(default_factory=list, max_length=42)
    office_id: Optional[str] = None
    office_nombre: Optional[str] = None

    @model_validator(mode="after")
    def validate_schedule(self):
        by_day = {}
        for block in self.horarios:
            by_day.setdefault(block.dia, []).append(block)
        for blocks in by_day.values():
            ordered = sorted(blocks, key=lambda block: block.desde)
            for previous, current in zip(ordered, ordered[1:]):
                if current.desde < previous.hasta:
                    raise ValueError("Los horarios del mismo día no pueden superponerse.")
        return self


class AmbienteCreate(AmbienteBase):
    pass


class Ambiente(AmbienteBase):
    id: str
    office_id: str
    created_at: Optional[str] = None


class TarifaAmbienteCreate(BaseModel):
    ambiente_id: str
    nombre: str = Field(min_length=1, max_length=120)
    modalidad: Literal["hora", "manana", "tarde", "dia", "actividad"]
    monto: Decimal = Field(gt=0)
    descripcion: Optional[str] = ""
    desde: Optional[str] = None
    hasta: Optional[str] = None

    @field_validator("nombre", mode="before")
    @classmethod
    def normalize_rental_tariff_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("monto")
    @classmethod
    def currency_precision(cls, value):
        if value.as_tuple().exponent < -2:
            raise ValueError("El monto debe tener como máximo dos decimales.")
        return value.quantize(Decimal("0.01"))

    @model_validator(mode="after")
    def validate_tariff_times(self):
        valid_time = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
        if self.modalidad in ("manana", "tarde"):
            if not self.desde or not self.hasta or not valid_time.fullmatch(self.desde) or not valid_time.fullmatch(self.hasta):
                raise ValueError("Indique un horario fijo válido HH:MM para esta modalidad.")
            if self.desde >= self.hasta:
                raise ValueError("La hora de fin debe ser posterior a la hora de inicio.")
        elif self.desde is not None or self.hasta is not None:
            raise ValueError("Esta modalidad no admite horarios fijos.")
        return self


class AlquilerCreate(BaseModel):
    ambiente_id: str
    tarifa_id: str
    fecha: str
    desde: Optional[str] = None
    hasta: Optional[str] = None
    cliente_tipo: Literal["persona", "estudiante"]
    cliente_id: str
    cliente_documento: Optional[str] = None
    cobrar_ahora: bool
    office_id: Optional[str] = None

    @field_validator("cliente_documento", mode="before")
    @classmethod
    def normalize_client_document(cls, value):
        return value.strip() if isinstance(value, str) else value


class PaginacionAmbientes(BaseModel):
    items: List[Ambiente]
    total: int
    page: int
    size: int
    pages: int


class PagoBase(BaseModel):
    id_estudiante: str
    fecha_pago: str  # YYYY-MM-DD
    office_id: Optional[str] = None
    office_nombre: Optional[str] = None
    # Optional for older clients that still submit a single concept at creation.
    id_tipo_pago: Optional[str] = None
    cantidad: Optional[float] = Field(default=None, gt=0)

class PagoCreate(PagoBase):
    pass


class PagoItemCreate(BaseModel):
    id_tipo_pago: str
    cantidad: float = Field(gt=0)


class PagoItem(BaseModel):
    id: Optional[str] = None
    id_tipo_pago: str
    tipo_pago_nombre: Optional[str] = None
    cantidad: float
    monto: float
    total: float


class Pago(PagoBase):
    id: str
    cod_comprobante: str
    gestion: int
    monto: float = 0
    total: float = 0
    items: List[PagoItem] = Field(default_factory=list)
    estado: Literal["borrador", "emitido"] = "emitido"
    prefijo_comprobante: Optional[str] = None
    comprobante_display: Optional[str] = None
    suboficina: Optional[str] = None
    estudiante_nombre: Optional[str] = None
    estudiante_ci: Optional[str] = None
    estudiante_cu: Optional[str] = ""
    tipo_pago_nombre: Optional[str] = None
    anulado: bool = False
    anulado_at: Optional[str] = None
    anulado_by: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    edited_at: Optional[str] = None
    edited_by: Optional[str] = None
    edited_by_name: Optional[str] = None

class PaginacionPagos(BaseModel):
    items: List[Pago]
    total: int
    page: int
    size: int
    pages: int


# ----------------------------- HELPERS -----------------------------
def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


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


def format_receipt_display(prefix: str, code: str, gestion: int) -> str:
    return f"{prefix.upper()}-{str(code).zfill(5)} / {int(gestion):04d}"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(user_id: str, email: str, rol: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "rol": rol,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRES_MIN),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido.")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")

    user = await db.usuarios.find_one({"id": user_id}, {"_id": 0})
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado.")
    return user


def require_roles(*allowed: str):
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if (
            user.get("rol") not in allowed
            and user.get("rol") != SUPER_ADMIN_ROLE
        ):
            raise HTTPException(
                status_code=403, detail="Sin permisos para esta acción."
            )
        return user

    return _dep


async def _office_exists(office_id: str, *, active: bool = False) -> dict:
    filt = {"id": office_id}
    if active:
        filt["activa"] = True
    office = await db.oficinas.find_one(filt, {"_id": 0})
    if not office:
        raise HTTPException(status_code=404, detail="Oficina no encontrada o inactiva.")
    return office


async def office_scope(
    user: dict, requested_office_id: Optional[str] = None
) -> dict:
    """Return a Mongo filter that confines non-super-admins to their office."""
    if user.get("rol") == SUPER_ADMIN_ROLE:
        if requested_office_id:
            await _office_exists(requested_office_id)
            return {"office_id": requested_office_id}
        return {}

    office_id = user.get("office_id")
    if not office_id:
        raise HTTPException(status_code=403, detail="El usuario no tiene una oficina asignada.")
    if requested_office_id and requested_office_id != office_id:
        raise HTTPException(status_code=403, detail="Sin permisos para consultar otra oficina.")
    return {"office_id": office_id}


async def office_for_write(
    user: dict, requested_office_id: Optional[str] = None
) -> str:
    """Resolve office ownership server-side for a new record."""
    if user.get("rol") == SUPER_ADMIN_ROLE:
        office_id = requested_office_id
        if not office_id:
            raise HTTPException(status_code=400, detail="Seleccione una oficina.")
        await _office_exists(office_id, active=True)
        return office_id

    office_id = user.get("office_id")
    if not office_id:
        raise HTTPException(status_code=403, detail="El usuario no tiene una oficina asignada.")
    if requested_office_id and requested_office_id != office_id:
        raise HTTPException(status_code=403, detail="No puede crear datos en otra oficina.")
    await _office_exists(office_id, active=True)
    return office_id


async def public_user(user: dict) -> UserPublic:
    doc = {key: value for key, value in user.items() if key not in ("_id", "password_hash")}
    office_id = doc.get("office_id")
    if office_id:
        office = await db.oficinas.find_one({"id": office_id}, {"_id": 0, "nombre": 1})
        doc["office_nombre"] = office.get("nombre") if office else None
    return UserPublic(**doc)


async def attach_office_names(items: List[dict]) -> List[dict]:
    ids = list({item.get("office_id") for item in items if item.get("office_id")})
    if not ids:
        return items
    offices = await db.oficinas.find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1, "nombre": 1}
    ).to_list(len(ids))
    names = {office["id"]: office["nombre"] for office in offices}
    for item in items:
        item["office_nombre"] = names.get(item.get("office_id"))
    return items


# ----------------------------- AUTH ENDPOINTS -----------------------------
@api.post("/auth/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(body: LoginRequest, response: Response):
    email = body.email.lower().strip()
    user = await db.usuarios.find_one({"email": email}, {"_id": 0})
    # Evitar revelar si el usuario existe o no
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas."
        )

    # Verificar contraseña
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas."
        )

    # Crear JWT
    token = create_access_token(user["id"], user["email"], user["rol"])
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRES_MIN * 60,
        path="/",
    )
    return {
        "token": token,
        "usuario": await public_user(user),
    }


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.get("/auth/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return await public_user(user)


# ----------------------------- Oficinas CRUD -----------------------------
@api.get("/oficinas", response_model=OfficePaginationResponse)
async def get_offices(
    pag: int = Query(1, ge=1),
    tam: int = Query(20, ge=1, le=100),
    q: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    filt = {} if user["rol"] == SUPER_ADMIN_ROLE else {"id": (await office_scope(user))["office_id"]}
    if q:
        filt["nombre"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    total = await db.oficinas.count_documents(filt)
    offices = await db.oficinas.find(filt, {"_id": 0}).sort("nombre", 1).skip(
        (pag - 1) * tam
    ).limit(tam).to_list(tam)
    return {
        "items": offices,
        "total": total,
        "page": pag,
        "size": tam,
        "pages": max(1, (total + tam - 1) // tam),
    }


@api.post("/oficinas", response_model=Office, status_code=201)
async def create_office(
    body: OfficeCreate, _: dict = Depends(require_roles(SUPER_ADMIN_ROLE))
):
    nombre = body.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Ingrese el nombre de la oficina.")
    doc = {
        "id": str(uuid.uuid4()),
        "nombre": nombre,
        "nombre_key": nombre.casefold(),
        "prefijo_comprobante": body.prefijo_comprobante,
        "suboficina": body.suboficina,
        "activa": body.activa,
        "created_at": iso(datetime.now(timezone.utc)),
    }
    try:
        await db.oficinas.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="La oficina o el prefijo ya existen.")
    return Office(**doc)


@api.put("/oficinas/{office_id}", response_model=Office)
async def update_office(
    office_id: str,
    body: OfficeCreate,
    _: dict = Depends(require_roles(SUPER_ADMIN_ROLE)),
):
    nombre = body.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Ingrese el nombre de la oficina.")
    try:
        result = await db.oficinas.update_one(
            {"id": office_id},
            {"$set": {
                "nombre": nombre,
                "nombre_key": nombre.casefold(),
                "prefijo_comprobante": body.prefijo_comprobante,
                "suboficina": body.suboficina,
                "activa": body.activa,
            }},
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="La oficina o el prefijo ya existen.")
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Oficina no encontrada.")
    return Office(**(await db.oficinas.find_one({"id": office_id}, {"_id": 0})))


@api.delete("/oficinas/{office_id}")
async def delete_office(
    office_id: str, _: dict = Depends(require_roles(SUPER_ADMIN_ROLE))
):
    await _office_exists(office_id)
    for collection in (
        db.usuarios,
        db.estudiantes,
        db.tipos_pagos,
        db.ambientes,
        db.pagos,
        db.tarifas_ambientes,
        db.alquileres,
    ):
        if await collection.find_one({"office_id": office_id}, {"_id": 1}):
            raise HTTPException(
                status_code=400,
                detail="No se puede eliminar una oficina con usuarios o registros asociados.",
            )
    await db.oficinas.delete_one({"id": office_id})
    return {"ok": True}


# ----------------------------- Users CRUD (admin) -----------------------------
@api.get("/usuarios", response_model=UserPaginationResponse)
async def get_users(
    pag: int = Query(1, ge=1, description="Número de página"),
    tam: int = Query(10, ge=1, le=100, description="Elementos por página"),
    office_id: Optional[str] = None,
    user: dict = Depends(require_roles("Administrador")),
):
    filt = await office_scope(user, office_id)
    salto = (pag - 1) * tam
    total_usuarios = await db.usuarios.count_documents(filt)
    cursor = db.usuarios.find(filt, {"_id": 0, "password_hash": 0}) \
                        .sort([("nombre", 1), ("email", 1)]) \
                        .skip(salto) \
                        .limit(tam)
    usuarios_dict = await cursor.to_list(length=tam)
    usuarios_validados = [await public_user(u) for u in usuarios_dict]
    total_paginas = (total_usuarios + tam - 1) // tam if total_usuarios > 0 else 1
    return {
        "items": usuarios_validados,
        "total": total_usuarios,
        "page": pag,
        "size": tam,
        "pages": total_paginas
    }

@api.get("/usuarios/list")
async def get_users_minimal(
    office_id: Optional[str] = None, user: dict = Depends(get_current_user)
):
    filt = await office_scope(user, office_id)
    cursor = db.usuarios.find(
        filt, {"_id": 0, "id": 1, "nombre": 1, "rol": 1, "office_id": 1}
    ).sort(
        "nombre", 1
    )
    return [u async for u in cursor]


@api.post("/usuarios", response_model=UserPublic, status_code=201)
async def create_user(
    usuario: UserCreate, current: dict = Depends(require_roles("Administrador"))
):
    email = usuario.email.lower().strip()
    if email == SUPER_ADMIN_EMAIL or await db.usuarios.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="El email ya está registrado.")
    office_id = await office_for_write(current, usuario.office_id)
    if usuario.rol == "Administrador":
        if current["rol"] != SUPER_ADMIN_ROLE:
            raise HTTPException(status_code=403, detail="Sólo el Super Admin asigna administradores.")
        if await db.usuarios.find_one({"office_id": office_id, "rol": "Administrador"}):
            raise HTTPException(status_code=400, detail="La oficina ya tiene un administrador.")
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "nombre": usuario.nombre,
        "rol": usuario.rol,
        "office_id": office_id,
        "password_hash": hash_password(usuario.password),
        "created_at": iso(datetime.now(timezone.utc)),
    }
    try:
        await db.usuarios.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="El email ya existe o la oficina ya tiene un administrador.")
    return await public_user(doc)


@api.put("/usuarios/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: str, usuario: UserUpdate, current: dict = Depends(require_roles("Administrador"))
):
    scope = await office_scope(current)
    target = await db.usuarios.find_one({"id": user_id, **scope}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if target["rol"] == SUPER_ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="La cuenta del Super Admin está protegida.")
    if current["rol"] != SUPER_ADMIN_ROLE:
        if target["rol"] == "Administrador" and target["id"] != current["id"]:
            raise HTTPException(status_code=403, detail="No puede modificar administradores.")
        if usuario.rol == "Administrador" and target["id"] != current["id"]:
            raise HTTPException(status_code=403, detail="Sólo el Super Admin asigna administradores.")
        if usuario.rol and target["id"] == current["id"] and usuario.rol != "Administrador":
            raise HTTPException(status_code=403, detail="No puede cambiar su propio rol.")

    update = {}
    if usuario.nombre is not None:
        update["nombre"] = usuario.nombre
    if usuario.rol is not None:
        update["rol"] = usuario.rol
    if usuario.password:
        update["password_hash"] = hash_password(usuario.password)
    office_id = target["office_id"]
    if usuario.office_id is not None:
        office_id = await office_for_write(current, usuario.office_id)
        if office_id != target["office_id"] and current["rol"] != SUPER_ADMIN_ROLE:
            raise HTTPException(status_code=403, detail="No puede mover usuarios de oficina.")
        update["office_id"] = office_id
    if update.get("rol") == "Administrador" or (
        target["rol"] == "Administrador" and office_id != target["office_id"]
    ):
        if current["rol"] != SUPER_ADMIN_ROLE and target["id"] != current["id"]:
            raise HTTPException(status_code=403, detail="Sólo el Super Admin asigna administradores.")
        existing = await db.usuarios.find_one(
            {"office_id": office_id, "rol": "Administrador", "id": {"$ne": user_id}}
        )
        if existing:
            raise HTTPException(status_code=400, detail="La oficina ya tiene un administrador.")
    if not update:
        raise HTTPException(status_code=400, detail="Sin cambios.")
    try:
        await db.usuarios.update_one({"id": user_id, **scope}, {"$set": update})
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="La oficina ya tiene un administrador.")
    updated = await db.usuarios.find_one(
        {"id": user_id}, {"_id": 0, "password_hash": 0}
    )
    return await public_user(updated)


@api.delete("/usuarios/{user_id}")
async def delete_user(
    user_id: str, current: dict = Depends(require_roles("Administrador"))
):
    if user_id == current["id"]:
        raise HTTPException(
            status_code=400, detail="No puedes eliminar tu propio usuario."
        )
    scope = await office_scope(current)
    target = await db.usuarios.find_one({"id": user_id, **scope}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if target.get("rol") == SUPER_ADMIN_ROLE or target.get("email") == SUPER_ADMIN_EMAIL:
        raise HTTPException(
            status_code=400, detail="No puedes eliminar el Super Admin."
        )
    if target["rol"] == "Administrador" and current["rol"] != SUPER_ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Sólo el Super Admin puede eliminar administradores.")
    await db.usuarios.delete_one({"id": user_id, **scope})
    return {"ok": True}


async def ensure_person_is_not_student(ci: str):
    normalized_ci = ci.strip()
    student = await db.estudiantes.find_one(
        {
            "ci": {
                "$regex": rf"^\s*{re.escape(normalized_ci)}\s*$",
                "$options": "i",
            }
        },
        {"_id": 1},
    )
    if student:
        raise HTTPException(
            status_code=400,
            detail="Esta persona está registrada como estudiante y no puede agregarse aquí.",
        )


async def ensure_student_is_not_person(ci: str):
    normalized_ci = ci.strip()
    person = await db.personas.find_one(
        {
            "ci": {
                "$regex": rf"^\s*{re.escape(normalized_ci)}\s*$",
                "$options": "i",
            }
        },
        {"_id": 1},
    )
    if person:
        raise HTTPException(
            status_code=400,
            detail="Este C.I. ya está registrado como Persona y no puede agregarse como estudiante.",
        )


# ----------------------------- CRUD Estudiantes -----------------------------
@api.get("/estudiantes", response_model=PaginacionEstudiantes)
async def get_estudiantes(
    pag: int = Query(1, ge=1, description="Número de página"),
    tam: int = Query(10, ge=1, le=100, description="Elementos por página"),
    textoBuscar: Optional[str] = None,
    office_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    filt = await office_scope(user, office_id)
    if textoBuscar:
        search = re.escape(textoBuscar.strip())
        filt["$or"] = [
            {"ci": {"$regex": search, "$options": "i"}},
            {"cu": {"$regex": search, "$options": "i"}},
            {"nombre": {"$regex": search, "$options": "i"}},
        ]
    salto = (pag - 1) * tam
    total_estudiantes = await db.estudiantes.count_documents(filt)
    cursor = db.estudiantes.find(filt, {"_id": 0}) \
                        .sort([("nombre", 1), ("cu", 1)]) \
                        .skip(salto) \
                        .limit(tam)
    estudiantes_dict = await attach_office_names(await cursor.to_list(length=tam))
    estudiantes_validados = [Estudiante(**u) for u in estudiantes_dict]
    total_paginas = (total_estudiantes + tam - 1) // tam if total_estudiantes > 0 else 1
    return {
        "items": estudiantes_validados,
        "total": total_estudiantes,
        "page": pag,
        "size": tam,
        "pages": total_paginas,
    }


@api.post("/estudiantes", response_model=Estudiante, status_code=201)
async def create_estudiante(
    estudiante: EstudianteCreate,
    user: dict = Depends(require_roles("Administrador", "Caja")),
):
    office_id = await office_for_write(user, estudiante.office_id)
    await ensure_student_is_not_person(estudiante.ci)
    if estudiante.cu and await db.estudiantes.find_one(
        {"office_id": office_id, "cu": estudiante.cu}
    ):
        raise HTTPException(status_code=400, detail="El estudiante ya existe.")
    estudiante_dict = estudiante.model_dump(exclude={"office_id", "office_nombre"})
    estudiante_dict.update({"id": str(uuid.uuid4()), "office_id": office_id})
    await db.estudiantes.insert_one(estudiante_dict)
    await attach_office_names([estudiante_dict])
    return Estudiante(**estudiante_dict)


@api.put("/estudiantes/{est_id}", response_model=Estudiante)
async def update_estudiante(
    est_id: str,
    estudiante: EstudianteCreate,
    user: dict = Depends(require_roles("Administrador")),
):
    scope = await office_scope(user)
    target = await db.estudiantes.find_one({"id": est_id, **scope}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    await ensure_student_is_not_person(estudiante.ci)
    if estudiante.office_id and estudiante.office_id != target["office_id"]:
        raise HTTPException(status_code=400, detail="No se puede cambiar la oficina de un estudiante.")
    if estudiante.cu and await db.estudiantes.find_one({
        "office_id": target["office_id"], "cu": estudiante.cu, "id": {"$ne": est_id}
    }):
        raise HTTPException(status_code=400, detail="El estudiante ya existe.")
    update = estudiante.model_dump(exclude={"office_id", "office_nombre"})
    await db.estudiantes.update_one({"id": est_id, **scope}, {"$set": update})
    updated = await db.estudiantes.find_one({"id": est_id}, {"_id": 0})
    await attach_office_names([updated])
    return Estudiante(**updated)


@api.delete("/estudiantes/{est_id}")
async def delete_estudiante(
    est_id: str, user: dict = Depends(require_roles("Administrador"))
):
    scope = await office_scope(user)
    target = await db.estudiantes.find_one({"id": est_id, **scope}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if await db.pagos.find_one({"id_estudiante": est_id, "office_id": target["office_id"]}):
        raise HTTPException(
            status_code=400, detail="No se puede eliminar: tiene pagos registrados."
        )
    await db.estudiantes.delete_one({"id": est_id, **scope})
    return {"ok": True}


# ----------------------------- CRUD Personas -----------------------------
@api.get("/personas", response_model=PaginacionPersonas)
async def get_personas(
    pag: int = Query(1, ge=1),
    tam: int = Query(20, ge=1, le=100),
    textoBuscar: Optional[str] = None,
    user: dict = Depends(require_roles("Administrador")),
):
    filt = {}
    if textoBuscar and textoBuscar.strip():
        search = re.escape(textoBuscar.strip())
        filt["$or"] = [
            {"ci": {"$regex": search, "$options": "i"}},
            {"nombre": {"$regex": search, "$options": "i"}},
        ]
    total = await db.personas.count_documents(filt)
    cursor = db.personas.find(filt, {"_id": 0}).sort(
        [("nombre", 1), ("ci", 1)]
    ).skip((pag - 1) * tam).limit(tam)
    personas = await cursor.to_list(length=tam)
    return {
        "items": [Persona(**item) for item in personas],
        "total": total,
        "page": pag,
        "size": tam,
        "pages": max(1, (total + tam - 1) // tam),
    }


@api.post("/personas", response_model=Persona, status_code=201)
async def create_persona(
    persona: PersonaCreate, user: dict = Depends(require_roles("Administrador"))
):
    await ensure_person_is_not_student(persona.ci)
    persona_dict = persona.model_dump()
    persona_dict.update(
        {
            "id": str(uuid.uuid4()),
            "ci_key": persona.ci.casefold(),
            "created_at": iso(datetime.now(timezone.utc)),
        }
    )
    try:
        await db.personas.insert_one(persona_dict)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=400,
            detail="Ya existe una persona registrada con este C.I.",
        )
    return Persona(**persona_dict)


@api.put("/personas/{persona_id}", response_model=Persona)
async def update_persona(
    persona_id: str,
    persona: PersonaCreate,
    user: dict = Depends(require_roles("Administrador")),
):
    target = await db.personas.find_one({"id": persona_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Persona no encontrada.")
    await ensure_person_is_not_student(persona.ci)
    update = persona.model_dump()
    update["ci_key"] = persona.ci.casefold()
    try:
        await db.personas.update_one({"id": persona_id}, {"$set": update})
    except DuplicateKeyError:
        raise HTTPException(
            status_code=400,
            detail="Ya existe una persona registrada con este C.I.",
        )
    updated = await db.personas.find_one({"id": persona_id}, {"_id": 0})
    return Persona(**updated)


@api.delete("/personas/{persona_id}")
async def delete_persona(
    persona_id: str, user: dict = Depends(require_roles("Administrador"))
):
    target = await db.personas.find_one({"id": persona_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Persona no encontrada.")
    await db.personas.delete_one({"id": persona_id})
    return {"ok": True}


# ----------------------------- CRUD TiposPagos -----------------------------
@api.get("/tipos-pagos", response_model=PaginacionTiposPagos)
async def get_tipos_pagos(
    pag: int = Query(1, ge=1, description="Número de página"),
    tam: int = Query(10, ge=1, le=100, description="Elementos por página"),
    activos: Optional[bool] = False,
    office_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    filt = await office_scope(user, office_id)
    if activos:
        today = date.today().isoformat()
        filt["inicio"] = {"$lte": today}
        filt["$or"] = [{"fin": None}, {"fin": {"$gte": today}}, {"fin": ""}]
    salto = (pag - 1) * tam
    total_tipos = await db.tipos_pagos.count_documents(filt)
    cursor = db.tipos_pagos.find(filt, {"_id": 0}) \
                        .sort([("nombre", 1), ("inicio", -1)]) \
                        .skip(salto) \
                        .limit(tam)
    tipos_dict = await attach_office_names(await cursor.to_list(length=tam))
    tipos_validados = [TipoPago(**t) for t in tipos_dict]
    total_paginas = (total_tipos + tam - 1) // tam if total_tipos > 0 else 1
    return {
        "items": tipos_validados,
        "total": total_tipos,
        "page": pag,
        "size": tam,
        "pages": total_paginas,
    }


@api.post("/tipos-pagos", response_model=TipoPago, status_code=201)
async def create_tipo_pago(
    tipo: TipoPagoCreate, user: dict = Depends(require_roles("Administrador"))
):
    office_id = await office_for_write(user, tipo.office_id)
    nombre = tipo.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Ingrese el nombre del tipo de pago.")
    tipo_dict = tipo.model_dump(exclude={"office_id", "office_nombre"})
    tipo_dict.update({
        "id": str(uuid.uuid4()), "office_id": office_id,
        "nombre": nombre, "nombre_key": nombre.casefold(),
    })
    try:
        await db.tipos_pagos.insert_one(tipo_dict)
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="El tipo de pago ya existe en esta oficina.")
    await attach_office_names([tipo_dict])
    return TipoPago(**tipo_dict)


@api.put("/tipos-pagos/{tipo_id}", response_model=TipoPago)
async def update_tipopago(
    tipo_id: str, tipo: TipoPagoCreate, user: dict = Depends(require_roles("Administrador"))
):
    scope = await office_scope(user)
    target = await db.tipos_pagos.find_one({"id": tipo_id, **scope}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado.")
    if tipo.office_id and tipo.office_id != target["office_id"]:
        raise HTTPException(status_code=400, detail="No se puede cambiar la oficina del tipo de pago.")
    nombre = tipo.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Ingrese el nombre del tipo de pago.")
    update = tipo.model_dump(exclude={"office_id", "office_nombre"})
    update.update({"nombre": nombre, "nombre_key": nombre.casefold()})
    try:
        await db.tipos_pagos.update_one({"id": tipo_id, **scope}, {"$set": update})
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="El tipo de pago ya existe en esta oficina.")
    updated = await db.tipos_pagos.find_one({"id": tipo_id}, {"_id": 0})
    await attach_office_names([updated])
    return TipoPago(**updated)


@api.delete("/tipos-pagos/{tipo_id}")
async def delete_tipo_pago(
    tipo_id: str, user: dict = Depends(require_roles("Administrador"))
):
    scope = await office_scope(user)
    target = await db.tipos_pagos.find_one({"id": tipo_id, **scope}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado.")
    if await db.pagos.find_one(
        {
            "office_id": target["office_id"],
            "$or": [
                {"id_tipo_pago": tipo_id},
                {"items.id_tipo_pago": tipo_id},
            ],
        }
    ):
        raise HTTPException(status_code=400, detail="No se puede eliminar: tiene pagos registrados.")
    await db.tipos_pagos.delete_one({"id": tipo_id, **scope})
    return {"ok": True}


# ----------------------------- CRUD Ambientes -----------------------------
@api.get("/ambientes", response_model=PaginacionAmbientes)
async def get_ambientes(
    pag: int = Query(1, ge=1),
    tam: int = Query(20, ge=1, le=100),
    office_id: Optional[str] = None,
    q: Optional[str] = None,
    user: dict = Depends(require_roles("Administrador", "Caja")),
):
    filt = await office_scope(user, office_id)
    if q and q.strip():
        filt["nombre"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    total = await db.ambientes.count_documents(filt)
    cursor = db.ambientes.find(filt, {"_id": 0}).sort(
        [("nombre_key", 1), ("nombre", 1)]
    ).skip((pag - 1) * tam).limit(tam)
    ambientes = await attach_office_names(await cursor.to_list(length=tam))
    return {
        "items": [Ambiente(**item) for item in ambientes],
        "total": total,
        "page": pag,
        "size": tam,
        "pages": max(1, (total + tam - 1) // tam),
    }


@api.post("/ambientes", response_model=Ambiente, status_code=201)
async def create_ambiente(
    ambiente: AmbienteCreate, user: dict = Depends(require_roles("Administrador"))
):
    office_id = await office_for_write(user, ambiente.office_id)
    nombre = ambiente.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Ingrese el nombre del ambiente.")
    ambiente_dict = ambiente.model_dump(exclude={"office_id", "office_nombre"})
    ambiente_dict.update(
        {
            "id": str(uuid.uuid4()),
            "office_id": office_id,
            "nombre": nombre,
            "nombre_key": nombre.casefold(),
            "created_at": iso(datetime.now(timezone.utc)),
        }
    )
    try:
        await db.ambientes.insert_one(ambiente_dict)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=400, detail="Ya existe un ambiente con ese nombre en esta oficina."
        )
    await attach_office_names([ambiente_dict])
    return Ambiente(**ambiente_dict)


@api.put("/ambientes/{ambiente_id}", response_model=Ambiente)
async def update_ambiente(
    ambiente_id: str,
    ambiente: AmbienteCreate,
    user: dict = Depends(require_roles("Administrador")),
):
    async with _ambiente_lease(ambiente_id) as lease_owner:
        return await _update_ambiente_under_lease(ambiente_id, ambiente, user, lease_owner)


async def _update_ambiente_under_lease(
    ambiente_id: str, ambiente: AmbienteCreate, user: dict, lease_owner: str
):
    scope = await office_scope(user)
    target = await db.ambientes.find_one(
        {"id": ambiente_id, **scope}, {"_id": 0}
    )
    if not target:
        raise HTTPException(status_code=404, detail="Ambiente no encontrado.")
    if ambiente.office_id and ambiente.office_id != target["office_id"]:
        raise HTTPException(
            status_code=400, detail="No se puede cambiar la oficina del ambiente."
        )
    nombre = ambiente.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Ingrese el nombre del ambiente.")
    update = ambiente.model_dump(exclude={"office_id", "office_nombre"})
    update.update({"nombre": nombre, "nombre_key": nombre.casefold()})
    proposed = {**target, **update}
    active_rentals = db.alquileres.find(
        {"ambiente_id": ambiente_id, "estado": {"$in": ["confirmando", "reservado", "procesando", "pagado"]}, "fecha": {"$gte": date.today().isoformat()}},
        {"_id": 0, "fecha": 1, "tramos": 1},
    )
    async for rental in active_rentals:
        blocks = _schedule_blocks(proposed, _validate_rental_date(rental["fecha"]))
        if any(not _covered_by_schedule(blocks, tramo["desde"], tramo["hasta"]) for tramo in rental.get("tramos", [])):
            raise HTTPException(status_code=400, detail="El cambio de horario invalidaría alquileres activos futuros.")
    try:
        write_result = await db.ambientes.update_one(
            {
                "id": ambiente_id,
                **scope,
                "_room_lease.owner": lease_owner,
                "_room_lease.lease_until": {"$gt": datetime.now(timezone.utc)},
            },
            {"$set": update},
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=400, detail="Ya existe un ambiente con ese nombre en esta oficina."
        )
    if not write_result.matched_count:
        raise HTTPException(status_code=409, detail="La exclusividad del ambiente expiró; vuelva a intentar.")
    updated = await db.ambientes.find_one({"id": ambiente_id}, {"_id": 0})
    await attach_office_names([updated])
    return Ambiente(**updated)


@api.delete("/ambientes/{ambiente_id}")
async def delete_ambiente(
    ambiente_id: str, user: dict = Depends(require_roles("Administrador"))
):
    async with _ambiente_lease(ambiente_id) as lease_owner:
        return await _delete_ambiente_under_lease(ambiente_id, user, lease_owner)


async def _delete_ambiente_under_lease(ambiente_id: str, user: dict, lease_owner: str):
    scope = await office_scope(user)
    target = await db.ambientes.find_one(
        {"id": ambiente_id, **scope}, {"_id": 0}
    )
    if not target:
        raise HTTPException(status_code=404, detail="Ambiente no encontrado.")
    if await db.alquileres.find_one({"ambiente_id": ambiente_id, "estado": {"$in": ["confirmando", "reservado", "procesando", "pagado"]}}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="No se puede eliminar un ambiente con alquileres activos.")
    if await db.tarifas_ambientes.find_one({"ambiente_id": ambiente_id}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="Elimine primero las tarifas asociadas al ambiente.")
    deleted = await db.ambientes.delete_one({
        "id": ambiente_id,
        **scope,
        "_room_lease.owner": lease_owner,
        "_room_lease.lease_until": {"$gt": datetime.now(timezone.utc)},
    })
    if not deleted.deleted_count:
        raise HTTPException(status_code=409, detail="La exclusividad del ambiente expiró; vuelva a intentar.")
    await db.alquiler_ocupacion.delete_many({
        "$or": [
            {"ambiente_id": ambiente_id},
            {"_id": {"$regex": f"^{re.escape(ambiente_id)}_"}},
        ],
    })
    return {"ok": True}


_RENTAL_ROLES = ("Administrador", "Caja")
_WEEKDAYS_ES = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_ROOM_LEASE_SECONDS = 120
_PAYMENT_LEASE_SECONDS = 120


@asynccontextmanager
async def _ambiente_lease(ambiente_id: str):
    """Cross-process exclusive lock for a room's schedule and booking mutations."""
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    try:
        acquired = await db.ambientes.find_one_and_update(
            {
                "id": ambiente_id,
                "$or": [
                    {"_room_lease.lease_until": {"$lte": now}},
                    {"_room_lease.lease_until": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "_room_lease.owner": token,
                    "_room_lease.lease_until": now + timedelta(seconds=_ROOM_LEASE_SECONDS),
                },
                "$inc": {"_room_lease.fence": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="El ambiente está siendo modificado o reservado.")
    if not acquired or acquired.get("_room_lease", {}).get("owner") != token:
        exists = await db.ambientes.find_one({"id": ambiente_id}, {"_id": 1})
        if not exists:
            raise HTTPException(status_code=404, detail="Ambiente no encontrado.")
        raise HTTPException(status_code=409, detail="El ambiente está siendo modificado o reservado.")
    try:
        yield token
    finally:
        await db.ambientes.update_one(
            {"id": ambiente_id, "_room_lease.owner": token},
            {"$set": {
                "_room_lease.owner": None,
                "_room_lease.lease_until": datetime.now(timezone.utc),
            }},
        )


async def _renew_ambiente_lease(ambiente_id: str, token: str):
    now = datetime.now(timezone.utc)
    renewed = await db.ambientes.update_one(
        {
            "id": ambiente_id,
            "_room_lease.owner": token,
            "_room_lease.lease_until": {"$gt": now},
        },
        {"$set": {
            "_room_lease.lease_until": now + timedelta(seconds=_ROOM_LEASE_SECONDS),
        }},
    )
    if not renewed.matched_count:
        raise HTTPException(
            status_code=409,
            detail="La reserva perdió la exclusividad del ambiente; vuelva a intentarlo.",
        )


async def _insert_rental_provisional(rental: dict):
    return await db.alquileres.insert_one(rental)


async def _confirm_rental_provisional(rental_id: str, confirmation_started_at: str):
    return await db.alquileres.update_one(
        {
            "id": rental_id,
            "estado": "confirmando",
            "confirmation_started_at": confirmation_started_at,
        },
        {
            "$set": {"estado": "reservado"},
            "$unset": {"confirmation_started_at": ""},
        },
    )


def _minute_of_day(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise HTTPException(status_code=400, detail="La hora debe tener formato HH:MM.")
    return int(value[:2]) * 60 + int(value[3:])


def _intervals_overlap(start: int, end: int, other_start: int, other_end: int) -> bool:
    """Half-open interval comparison; adjacent bookings do not collide."""
    return start < other_end and end > other_start


def _schedule_blocks(ambiente: dict, rental_date: date) -> list:
    day_name = _WEEKDAYS_ES[rental_date.weekday()]
    return sorted(
        [(block["desde"], block["hasta"]) for block in ambiente.get("horarios", []) if block.get("dia") == day_name],
        key=lambda block: block[0],
    )


def _covered_by_schedule(blocks: list, start: str, end: str) -> bool:
    start_min, end_min = _minute_of_day(start), _minute_of_day(end)
    # Merge touching registered blocks so a continuous interval can span their boundary.
    merged = []
    for block_start, block_end in blocks:
        if merged and block_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], block_end))
        else:
            merged.append((block_start, block_end))
    return any(_minute_of_day(a) <= start_min and _minute_of_day(b) >= end_min for a, b in merged)


async def _rental_scope_record(rental_id: str, user: dict) -> dict:
    rental = await db.alquileres.find_one({"id": rental_id}, {"_id": 0})
    if not rental:
        raise HTTPException(status_code=404, detail="Alquiler no encontrado.")
    await office_scope(user, rental.get("office_id"))
    office = await db.oficinas.find_one(
        {"id": rental.get("office_id")}, {"_id": 0, "suboficina": 1}
    )
    rental["suboficina"] = (office or {}).get("suboficina", "") or ""
    return rental


@api.get("/tarifas-ambientes")
async def get_tarifas_ambientes(
    ambiente_id: str,
    user: dict = Depends(require_roles("Administrador", "Caja")),
):
    ambiente = await db.ambientes.find_one({"id": ambiente_id}, {"_id": 0})
    if not ambiente:
        raise HTTPException(status_code=404, detail="Ambiente no encontrado.")
    await office_scope(user, ambiente["office_id"])
    return await db.tarifas_ambientes.find({"ambiente_id": ambiente_id}, {"_id": 0}).sort("nombre", 1).to_list(500)


@api.post("/tarifas-ambientes", status_code=201)
async def create_tarifa_ambiente(
    body: TarifaAmbienteCreate, user: dict = Depends(require_roles("Administrador"))
):
    ambiente = await db.ambientes.find_one({"id": body.ambiente_id}, {"_id": 0})
    if not ambiente:
        raise HTTPException(status_code=404, detail="Ambiente no encontrado.")
    await office_scope(user, ambiente["office_id"])
    doc = body.model_dump()
    doc.update({"id": str(uuid.uuid4()), "office_id": ambiente["office_id"], "monto": float(body.monto), "created_at": iso(datetime.now(timezone.utc))})
    await db.tarifas_ambientes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/tarifas-ambientes/{tarifa_id}")
async def update_tarifa_ambiente(
    tarifa_id: str, body: TarifaAmbienteCreate, user: dict = Depends(require_roles("Administrador"))
):
    target = await db.tarifas_ambientes.find_one({"id": tarifa_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Tarifa no encontrada.")
    await office_scope(user, target["office_id"])
    if body.ambiente_id != target["ambiente_id"]:
        raise HTTPException(status_code=400, detail="No se puede cambiar el ambiente de una tarifa.")
    update = body.model_dump()
    update["monto"] = float(body.monto)
    await db.tarifas_ambientes.update_one({"id": tarifa_id}, {"$set": update})
    return await db.tarifas_ambientes.find_one({"id": tarifa_id}, {"_id": 0})


@api.delete("/tarifas-ambientes/{tarifa_id}")
async def delete_tarifa_ambiente(
    tarifa_id: str, user: dict = Depends(require_roles("Administrador"))
):
    target = await db.tarifas_ambientes.find_one({"id": tarifa_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Tarifa no encontrada.")
    await office_scope(user, target["office_id"])
    await db.tarifas_ambientes.delete_one({"id": tarifa_id})
    return {"ok": True}


@api.get("/alquileres/clientes")
async def search_alquiler_clientes(q: str = "", user: dict = Depends(require_roles(*_RENTAL_ROLES))):
    term = q.strip()
    if len(term) < 2:
        return []
    pattern = re.escape(term)
    personas = await db.personas.find(
        {"$or": [{"ci": {"$regex": pattern, "$options": "i"}}, {"nombre": {"$regex": pattern, "$options": "i"}}]},
        {"_id": 0, "id": 1, "nombre": 1, "ci": 1},
    ).sort("nombre", 1).limit(20).to_list(20)
    matches = [{"tipo": "persona", "id": item["id"], "nombre": item["nombre"], "ci": item["ci"]} for item in personas]

    projection = {"_id": 0, "id": 1, "nombre": 1, "ci": 1, "cu": 1, "office_id": 1}
    student_search = {"$or": [
        {"ci": {"$regex": pattern, "$options": "i"}},
        {"cu": {"$regex": pattern, "$options": "i"}},
        {"nombre": {"$regex": pattern, "$options": "i"}},
    ]}
    if user.get("rol") == SUPER_ADMIN_ROLE:
        students = await db.estudiantes.find(student_search, projection).sort("nombre", 1).limit(20).to_list(20)
    else:
        own_office_id = (await office_scope(user))["office_id"]
        own_filter = {"$and": [{"office_id": own_office_id}, student_search]}
        students = await db.estudiantes.find(own_filter, projection).sort("nombre", 1).limit(20).to_list(20)
        remaining = 20 - len(students)
        if len(term) >= 3 and remaining:
            exact = {"$regex": rf"^\s*{pattern}\s*$", "$options": "i"}
            cross_filter = {
                "$and": [
                    {"office_id": {"$exists": True, "$ne": own_office_id}},
                    {"$or": [{"ci": exact}, {"cu": exact}]},
                ]
            }
            cross_office_students = await db.estudiantes.find(
                cross_filter, projection
            ).sort("nombre", 1).limit(remaining).to_list(remaining)
            students.extend(cross_office_students)
    await attach_office_names(students)
    for item in students:
        entry = {
            "tipo": "estudiante", "id": item["id"], "nombre": item["nombre"],
            "ci": item["ci"], "office_nombre": item.get("office_nombre"),
        }
        if item.get("cu") is not None:
            entry["cu"] = item.get("cu")
        matches.append(entry)
    return matches


@api.post("/alquileres/clientes/persona", response_model=Persona, status_code=201)
async def create_alquiler_persona(
    persona: PersonaCreate,
    user: dict = Depends(require_roles(*_RENTAL_ROLES)),
):
    return await create_persona(persona, user)


def _validate_rental_date(text: str) -> date:
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
        if parsed.isoformat() != text:
            raise ValueError
        return parsed
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="La fecha debe tener formato YYYY-MM-DD.")


async def _build_rental(user: dict, body: AlquilerCreate) -> dict:
    rental_day = _validate_rental_date(body.fecha)
    ambiente = await db.ambientes.find_one({"id": body.ambiente_id}, {"_id": 0})
    if not ambiente:
        raise HTTPException(status_code=404, detail="Ambiente no encontrado.")
    await office_scope(user, ambiente["office_id"])
    tariff = await db.tarifas_ambientes.find_one({"id": body.tarifa_id, "ambiente_id": body.ambiente_id}, {"_id": 0})
    if not tariff:
        raise HTTPException(status_code=400, detail="La tarifa no pertenece al ambiente seleccionado.")
    if body.office_id and body.office_id != ambiente["office_id"]:
        raise HTTPException(status_code=400, detail="La oficina no coincide con el ambiente.")
    payer_collection = db.personas if body.cliente_tipo == "persona" else db.estudiantes
    payer_filter = {"id": body.cliente_id}
    if body.cliente_tipo == "estudiante":
        # Student ownership does not constrain rental venue ownership.
        pass
    payer = await payer_collection.find_one(payer_filter, {"_id": 0})
    if not payer:
        raise HTTPException(status_code=400, detail="El cliente seleccionado no existe.")
    if (
        body.cliente_tipo == "estudiante"
        and user.get("rol") != SUPER_ADMIN_ROLE
        and payer.get("office_id") != ambiente["office_id"]
    ):
        proof = (body.cliente_documento or "").strip().casefold()
        valid_documents = {
            str(payer.get("ci", "")).strip().casefold(),
            str(payer.get("cu", "")).strip().casefold(),
        }
        valid_documents.discard("")
        if not proof or proof not in valid_documents:
            raise HTTPException(
                status_code=400,
                detail="Para un estudiante de otra oficina, confirme su C.I. o C.U.",
            )
    blocks = _schedule_blocks(ambiente, rental_day)
    modalidad = tariff["modalidad"]
    if modalidad in ("hora", "actividad"):
        if not body.desde or not body.hasta:
            raise HTTPException(status_code=400, detail="Indique las horas de inicio y fin.")
        start_min, end_min = _minute_of_day(body.desde), _minute_of_day(body.hasta)
        if start_min >= end_min:
            raise HTTPException(status_code=400, detail="La hora de fin debe ser posterior al inicio.")
        if not _covered_by_schedule(blocks, body.desde, body.hasta):
            raise HTTPException(status_code=400, detail="El horario solicitado no está cubierto por un bloque disponible.")
        tramos = [{"desde": body.desde, "hasta": body.hasta}]
    elif modalidad in ("manana", "tarde"):
        if body.desde is not None and body.desde != tariff["desde"] or body.hasta is not None and body.hasta != tariff["hasta"]:
            raise HTTPException(status_code=400, detail="El horario debe coincidir con la tarifa.")
        if not _covered_by_schedule(blocks, tariff["desde"], tariff["hasta"]):
            raise HTTPException(status_code=400, detail="La tarifa no está cubierta por el horario disponible.")
        tramos = [{"desde": tariff["desde"], "hasta": tariff["hasta"]}]
    else:
        if body.desde is not None or body.hasta is not None:
            raise HTTPException(status_code=400, detail="La modalidad día no admite horas.")
        if not blocks:
            raise HTTPException(status_code=400, detail="El ambiente no tiene horario disponible ese día.")
        tramos = [{"desde": a, "hasta": b} for a, b in blocks]
    cents = int((Decimal(str(tariff["monto"])) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    quantity = Decimal("1")
    if modalidad == "hora":
        minutes = _minute_of_day(tramos[0]["hasta"]) - _minute_of_day(tramos[0]["desde"])
        quantity = Decimal(minutes) / Decimal(60)
        total_cents = int((Decimal(cents) * quantity).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        total_cents = cents
    office = await _office_exists(ambiente["office_id"], active=True)
    rental_id = str(uuid.uuid4())
    intervals = []
    for tramo in tramos:
        intervals.append({
            "rental_id": rental_id,
            "start": _minute_of_day(tramo["desde"]),
            "end": _minute_of_day(tramo["hasta"]),
        })
    return {
        "id": rental_id, "office_id": ambiente["office_id"], "office_nombre": office["nombre"],
        "suboficina": office.get("suboficina", "") or "",
        "ambiente_id": ambiente["id"], "ambiente_nombre": ambiente["nombre"], "fecha": body.fecha,
        "tramos": tramos, "cliente_tipo": body.cliente_tipo, "cliente_id": payer["id"],
        "cliente_nombre": payer["nombre"], "cliente_ci": payer["ci"],
        "cliente_cu": payer.get("cu") if body.cliente_tipo == "estudiante" else None,
        "tarifa_id": tariff["id"], "tarifa_nombre": tariff["nombre"], "modalidad": modalidad,
        "monto": cents / 100, "cantidad": float(quantity), "total": total_cents / 100,
        "estado": "reservado", "cod_comprobante": None, "gestion": None,
        "prefijo_comprobante": None, "comprobante_display": None, "fecha_pago": None,
        "created_at": iso(datetime.now(timezone.utc)), "intervals": intervals,
    }


async def _claim_rental_intervals(rental: dict):
    # Callers hold the per-room lease, so canceled entries and sufficiently old
    # orphan claims can be reaped without racing an in-flight booking insert.
    occupancy_id = f'{rental["ambiente_id"]}_{rental["fecha"]}'
    current_occupancy = await db.alquiler_ocupacion.find_one(
        {"_id": occupancy_id}, {"_id": 1, "intervals": 1}
    )
    if current_occupancy:
        await _reap_stale_occupancy_claims(current_occupancy)
    claimed_at = iso(datetime.now(timezone.utc))
    for interval in rental["intervals"]:
        interval["claimed_at"] = claimed_at
    overlaps = [{"intervals": {"$elemMatch": {"start": {"$lt": interval["end"]}, "end": {"$gt": interval["start"]}}}} for interval in rental["intervals"]]
    query = {"_id": occupancy_id, "$nor": overlaps}
    try:
        await db.alquiler_ocupacion.update_one(
            query,
            {"$setOnInsert": {"ambiente_id": rental["ambiente_id"], "fecha": rental["fecha"]}, "$push": {"intervals": {"$each": rental["intervals"]}}},
            upsert=True,
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="El horario solicitado ya está reservado.")


async def _release_rental_intervals(rental: dict):
    await db.alquiler_ocupacion.update_one(
        {"_id": f'{rental["ambiente_id"]}_{rental["fecha"]}'},
        {"$pull": {"intervals": {"rental_id": rental["id"]}}},
    )


def _claim_is_expired(claimed_at, cutoff: datetime) -> bool:
    if isinstance(claimed_at, str):
        try:
            claimed_at = datetime.fromisoformat(claimed_at)
        except ValueError:
            return False
    if not isinstance(claimed_at, datetime):
        return False
    if claimed_at.tzinfo is None:
        claimed_at = claimed_at.replace(tzinfo=timezone.utc)
    return claimed_at.astimezone(timezone.utc) <= cutoff


async def _pull_occupancy_rental_claim(occupancy_id: str, rental_id: str):
    await db.alquiler_ocupacion.update_one(
        {"_id": occupancy_id},
        {"$pull": {"intervals": {"rental_id": rental_id}}},
    )


async def _cancel_stale_confirmando(rental: dict, cutoff: datetime) -> bool:
    started_at = rental.get("confirmation_started_at")
    if not _claim_is_expired(started_at, cutoff):
        return False
    canceled = await db.alquileres.update_one(
        {
            "id": rental["id"],
            "estado": "confirmando",
            "confirmation_started_at": started_at,
        },
        {
            "$set": {"estado": "cancelado"},
            "$unset": {"confirmation_started_at": ""},
        },
    )
    if canceled.modified_count:
        await _release_rental_intervals(rental)
        return True
    return False


async def _reap_stale_occupancy_claims(occupancy: dict):
    intervals = occupancy.get("intervals", [])
    grouped = {}
    for interval in intervals:
        rental_id = interval.get("rental_id")
        if rental_id:
            grouped.setdefault(rental_id, []).append(interval)
    if not grouped:
        return
    rentals = await db.alquileres.find(
        {"id": {"$in": list(grouped)}},
        {
            "_id": 0, "id": 1, "estado": 1, "confirmation_started_at": 1,
            "ambiente_id": 1, "fecha": 1,
        },
    ).to_list(len(grouped))
    rental_by_id = {rental["id"]: rental for rental in rentals}
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=_ROOM_LEASE_SECONDS + 30)
    stale_ids = []
    for rental_id, rental_intervals in grouped.items():
        existing_rental = rental_by_id.get(rental_id)
        state = existing_rental.get("estado") if existing_rental else None
        if state == "confirmando" and await _cancel_stale_confirmando(existing_rental, cutoff):
            stale_ids.append(rental_id)
        elif state == "cancelado":
            stale_ids.append(rental_id)
        elif existing_rental is None and all(
            _claim_is_expired(interval.get("claimed_at"), cutoff)
            for interval in rental_intervals
        ):
            # Missing claimed_at is legacy/ambiguous and is intentionally
            # preserved rather than risking deletion of an in-flight claim.
            if all(interval.get("claimed_at") is not None for interval in rental_intervals):
                stale_ids.append(rental_id)
    for rental_id in stale_ids:
        await _pull_occupancy_rental_claim(occupancy["_id"], rental_id)


async def reconcile_rental_occupancy():
    """Restore occupancy invariants after interrupted booking/payment work."""
    now_iso = iso(datetime.now(timezone.utc))
    await db.alquileres.update_many(
        {
            "estado": "procesando",
            "$or": [
                {"processing_lease_until": {"$lte": now_iso}},
            ],
        },
        {
            "$set": {"estado": "reservado"},
            "$unset": {
                "payment_token": "", "processing_lease_until": "",
                "processing_started_at": "",
            },
        },
    )
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=_ROOM_LEASE_SECONDS + 30)
    async for provisional in db.alquileres.find(
        {"estado": "confirmando"},
        {
            "_id": 0, "id": 1, "ambiente_id": 1, "fecha": 1,
            "confirmation_started_at": 1,
        },
    ):
        if not _claim_is_expired(provisional.get("confirmation_started_at"), cutoff):
            continue
        try:
            async with _ambiente_lease(provisional["ambiente_id"]):
                current = await db.alquileres.find_one(
                    {"id": provisional["id"], "estado": "confirmando"},
                    {
                        "_id": 0, "id": 1, "ambiente_id": 1, "fecha": 1,
                        "confirmation_started_at": 1,
                    },
                )
                if current:
                    await _cancel_stale_confirmando(current, cutoff)
        except HTTPException as exc:
            if exc.status_code == 404:
                logger.info(
                    "Se omite confirmación provisional de ambiente eliminado: %s",
                    provisional["id"],
                )
                continue
            if exc.status_code != 409:
                raise
    async for occupancy in db.alquiler_ocupacion.find(
        {}, {"_id": 1, "ambiente_id": 1, "intervals": 1}
    ):
        ambiente_id = occupancy.get("ambiente_id") or occupancy["_id"].rsplit("_", 1)[0]
        try:
            async with _ambiente_lease(ambiente_id):
                current_occupancy = await db.alquiler_ocupacion.find_one(
                    {"_id": occupancy["_id"]},
                    {"_id": 1, "intervals": 1},
                )
                if current_occupancy:
                    await _reap_stale_occupancy_claims(current_occupancy)
        except HTTPException as exc:
            if exc.status_code == 404:
                logger.info(
                    "Se omite ocupación huérfana de ambiente eliminado: %s",
                    occupancy["_id"],
                )
                continue
            if exc.status_code != 409:
                raise


async def _finalize_rental_payment(rental_id: str, payment_token: str, update: dict):
    return await db.alquileres.update_one(
        {"id": rental_id, "estado": "procesando", "payment_token": payment_token},
        {
            "$set": update,
            "$unset": {
                "payment_token": "", "processing_lease_until": "",
                "processing_started_at": "",
            },
        },
    )


async def _pay_rental(rental_id: str, user: dict) -> dict:
    rental = await _rental_scope_record(rental_id, user)
    if rental["estado"] == "pagado":
        return rental
    now_iso = iso(datetime.now(timezone.utc))
    if rental["estado"] == "procesando":
        lease_until = rental.get("processing_lease_until")
        if not lease_until:
            raise HTTPException(
                status_code=409,
                detail="El pago no tiene una expiración verificable y requiere recuperación segura.",
            )
        if lease_until > now_iso:
            raise HTTPException(status_code=409, detail="El pago del alquiler ya está siendo procesado.")
        stale_filter = {"id": rental_id, "estado": "procesando"}
        stale_filter["processing_lease_until"] = lease_until
        recovered = await db.alquileres.update_one(
            stale_filter,
            {
                "$set": {"estado": "reservado"},
                "$unset": {"payment_token": "", "processing_lease_until": "", "processing_started_at": ""},
            },
        )
        if not recovered.modified_count:
            latest = await db.alquileres.find_one({"id": rental_id}, {"_id": 0})
            if latest and latest.get("estado") == "pagado":
                return latest
            raise HTTPException(status_code=409, detail="El pago del alquiler ya está siendo procesado.")
    elif rental["estado"] != "reservado":
        raise HTTPException(status_code=400, detail="Solo se puede pagar un alquiler reservado.")

    payment_token = str(uuid.uuid4())
    started_at = iso(datetime.now(timezone.utc))
    claimed = await db.alquileres.update_one(
        {"id": rental_id, "estado": "reservado"},
        {"$set": {
            "estado": "procesando",
            "payment_token": payment_token,
            "processing_started_at": started_at,
            "processing_lease_until": iso(
                datetime.now(timezone.utc) + timedelta(seconds=_PAYMENT_LEASE_SECONDS)
            ),
        }},
    )
    if not claimed.modified_count:
        latest = await db.alquileres.find_one({"id": rental_id}, {"_id": 0})
        if latest and latest.get("estado") == "pagado":
            return latest
        raise HTTPException(status_code=409, detail="El alquiler está siendo procesado.")
    try:
        year = datetime.now(timezone.utc).year
        office = await _office_exists(rental["office_id"], active=True)
        counter = await db.contadores.find_one_and_update(
            {"_id": f'comprobante_{rental["office_id"]}_{year}'},
            {"$inc": {"seq": 1}}, upsert=True, return_document=True,
        )
        code = f'{counter["seq"]:05d}'
        paid_at = iso(datetime.now(timezone.utc))
        update = {
            "estado": "pagado", "cod_comprobante": code, "gestion": year,
            "prefijo_comprobante": office["prefijo_comprobante"],
            "comprobante_display": format_receipt_display(office["prefijo_comprobante"], code, year),
            "fecha_pago": paid_at, "paid_by": user["id"],
        }
        # Counter allocation intentionally precedes the paid transition. A
        # database failure can leave a skipped sequence; reusing it risks a
        # duplicate receipt across Pagos and room rentals.
        paid_result = await _finalize_rental_payment(rental_id, payment_token, update)
        if not paid_result.modified_count:
            raise RuntimeError("El alquiler dejó de estar disponible durante la emisión.")
    except Exception as exc:
        await db.alquileres.update_one(
            {"id": rental_id, "estado": "procesando", "payment_token": payment_token},
            {
                "$set": {"estado": "reservado"},
                "$unset": {
                    "payment_token": "", "processing_lease_until": "",
                    "processing_started_at": "",
                },
            },
        )
        if isinstance(exc, HTTPException):
            raise exc
        logging.exception("Fallo al emitir comprobante de alquiler %s", rental_id)
        raise HTTPException(status_code=500, detail=f"No se pudo emitir el comprobante. La reserva {rental_id} sigue guardada.")
    return await db.alquileres.find_one({"id": rental_id}, {"_id": 0})


@api.get("/alquileres")
async def get_alquileres(
    ambiente_id: str, fecha_desde: str, fecha_hasta: str, office_id: Optional[str] = None,
    user: dict = Depends(require_roles(*_RENTAL_ROLES)),
):
    start, end = _validate_rental_date(fecha_desde), _validate_rental_date(fecha_hasta)
    if end < start or (end - start).days > 366:
        raise HTTPException(status_code=400, detail="Rango de fechas inválido.")
    ambiente = await db.ambientes.find_one({"id": ambiente_id}, {"_id": 0})
    if not ambiente:
        raise HTTPException(status_code=404, detail="Ambiente no encontrado.")
    await office_scope(user, office_id or ambiente["office_id"])
    if office_id and office_id != ambiente["office_id"]:
        raise HTTPException(status_code=404, detail="Ambiente no encontrado en esa oficina.")
    return await db.alquileres.find(
        {
            "ambiente_id": ambiente_id,
            "fecha": {"$gte": fecha_desde, "$lte": fecha_hasta},
            "estado": {"$ne": "confirmando"},
        },
        {"_id": 0, "intervals": 0},
    ).sort([("fecha", 1), ("created_at", 1)]).to_list(None)


@api.get("/alquileres/{rental_id}")
async def get_alquiler(rental_id: str, user: dict = Depends(require_roles(*_RENTAL_ROLES))):
    rental = await _rental_scope_record(rental_id, user)
    if rental.get("estado") == "confirmando":
        raise HTTPException(status_code=404, detail="Alquiler no encontrado.")
    rental.pop("intervals", None)
    return rental


@api.post("/alquileres", status_code=201)
async def create_alquiler(body: AlquilerCreate, user: dict = Depends(require_roles(*_RENTAL_ROLES))):
    async with _ambiente_lease(body.ambiente_id) as lease_owner:
        # Room schedule and active reservations are read only after acquiring
        # the same lease used by schedule updates/deletes.
        rental = await _build_rental(user, body)
        confirmation_started_at = iso(datetime.now(timezone.utc))
        rental["estado"] = "confirmando"
        rental["confirmation_started_at"] = confirmation_started_at
        try:
            await _claim_rental_intervals(rental)
            await _insert_rental_provisional(rental)
            # Confirming records keep schedules and occupancy protected if the
            # lease expires while the insert/confirmation flow is paused.
            await _renew_ambiente_lease(body.ambiente_id, lease_owner)
            confirmed = await _confirm_rental_provisional(
                rental["id"], confirmation_started_at
            )
            if not confirmed.modified_count:
                raise HTTPException(
                    status_code=409,
                    detail="La reserva perdió la exclusividad del ambiente; vuelva a intentarlo.",
                )
            rental["estado"] = "reservado"
            rental.pop("confirmation_started_at", None)
        except Exception as exc:
            cancellation_won = False
            try:
                cancellation = await db.alquileres.update_one(
                    {
                        "id": rental["id"],
                        "estado": "confirmando",
                        "confirmation_started_at": confirmation_started_at,
                    },
                    {
                        "$set": {"estado": "cancelado"},
                        "$unset": {"confirmation_started_at": ""},
                    },
                )
                cancellation_won = bool(cancellation.modified_count)
            except Exception:
                # The cancellation write can also have an unknown outcome;
                # verify persisted state before deciding whether to release.
                logging.exception("No se pudo confirmar la cancelación provisional %s", rental["id"])

            may_release = cancellation_won
            persisted = None
            if not may_release:
                try:
                    persisted = await db.alquileres.find_one(
                        {"id": rental["id"]}, {"_id": 0, "estado": 1}
                    )
                    may_release = (
                        persisted is None or persisted.get("estado") == "cancelado"
                    )
                except Exception:
                    logging.exception("No se pudo verificar el estado de la reserva %s", rental["id"])

            if may_release:
                try:
                    await _release_rental_intervals(rental)
                except Exception:
                    logging.exception("No se pudieron liberar intervalos de reserva cancelada %s", rental["id"])
                raise

            # Conservatively retain occupancy whenever the record may still be
            # active or its state cannot be verified.
            logging.exception("Resultado incierto al confirmar reserva %s", rental["id"], exc_info=exc)
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo verificar la confirmación. Consulte la reserva {rental['id']} antes de reintentar.",
            ) from exc
    rental.pop("_id", None)
    rental.pop("intervals", None)
    if body.cobrar_ahora:
        try:
            paid = await _pay_rental(rental["id"], user)
            paid.pop("intervals", None)
            return paid
        except HTTPException as exc:
            raise HTTPException(status_code=exc.status_code, detail=f"{exc.detail} Reserva guardada: {rental['id']}.")
    return rental


@api.post("/alquileres/{rental_id}/pagar")
async def pay_alquiler(rental_id: str, user: dict = Depends(require_roles(*_RENTAL_ROLES))):
    rental = await _pay_rental(rental_id, user)
    rental.pop("intervals", None)
    return rental


@api.post("/alquileres/{rental_id}/cancelar")
async def cancel_alquiler(rental_id: str, user: dict = Depends(require_roles(*_RENTAL_ROLES))):
    rental = await _rental_scope_record(rental_id, user)
    if rental.get("estado") != "cancelado":
        if rental.get("estado") != "reservado":
            raise HTTPException(status_code=400, detail="Solo se puede cancelar un alquiler reservado.")
        result = await db.alquileres.update_one(
            {"id": rental_id, "estado": "reservado"}, {"$set": {"estado": "cancelado"}}
        )
        if not result.modified_count:
            latest = await db.alquileres.find_one({"id": rental_id}, {"_id": 0})
            if not latest or latest.get("estado") != "cancelado":
                raise HTTPException(status_code=400, detail="Solo se puede cancelar un alquiler reservado.")
            rental = latest

    # Also clear any leftover claims on retries of an already-canceled rental.
    await _release_rental_intervals(rental)
    return await db.alquileres.find_one({"id": rental_id}, {"_id": 0, "intervals": 0})


@api.post("/alquileres/{rental_id}/anular")
async def anular_comprobante_alquiler(
    rental_id: str, user: dict = Depends(require_roles("Administrador", "Caja"))
):
    rental = await _rental_scope_record(rental_id, user)
    if (
        not rental.get("cod_comprobante")
        or rental.get("estado") not in {"pagado", "cancelado"}
    ):
        raise HTTPException(
            status_code=400,
            detail="Solo se puede anular un comprobante de alquiler pagado.",
        )
    if user.get("rol") == "Caja":
        if rental.get("paid_by") != user.get("id"):
            raise HTTPException(
                status_code=403,
                detail="Caja solo puede anular sus propios comprobantes.",
            )
        if _printed_payment_date(rental.get("fecha_pago")) != _current_bolivia_date():
            raise HTTPException(
                status_code=403,
                detail="Caja solo puede anular sus comprobantes el día de la fecha impresa.",
            )

    if rental.get("estado") != "cancelado":
        result = await db.alquileres.update_one(
            {
                "id": rental_id,
                "office_id": rental["office_id"],
                "estado": "pagado",
                "cod_comprobante": rental["cod_comprobante"],
            },
            {"$set": {"estado": "cancelado"}},
        )
        if not result.modified_count:
            latest = await db.alquileres.find_one(
                {"id": rental_id, "office_id": rental["office_id"]}, {"_id": 0}
            )
            if (
                not latest
                or latest.get("estado") != "cancelado"
                or not latest.get("cod_comprobante")
            ):
                raise HTTPException(
                    status_code=409,
                    detail="El comprobante cambió de estado; vuelva a consultarlo.",
                )
            rental = latest

    # Keep the receipt number and rental record for audit, but release its room.
    await _release_rental_intervals(rental)
    return await db.alquileres.find_one(
        {"id": rental_id}, {"_id": 0, "intervals": 0}
    )


# ----------------------------- Pagos: comprobante preview -----------------------------
@api.get("/pagos/preview-comprobante")
async def preview_comprobante(
    office_id: Optional[str] = None,
    user: dict = Depends(require_roles("Administrador", "Caja")),
):
    selected_office_id = await office_for_write(user, office_id)
    office = await _office_exists(selected_office_id, active=True)
    gestion = datetime.now(timezone.utc).year
    counter_id = f"comprobante_{selected_office_id}_{gestion}"
    counter = await db.contadores.find_one({"_id": counter_id})
    siguiente_num = (counter["seq"] if counter else 0) + 1
    codigo = f"{siguiente_num:05d}"
    return {
        "cod_comprobante": codigo,
        "gestion": gestion,
        "prefijo_comprobante": office["prefijo_comprobante"],
        "office_id": selected_office_id,
        "display": format_receipt_display(office["prefijo_comprobante"], codigo, gestion),
    }


# ----------------------------- Pagos CRUD -----------------------------
# Aggregation pipeline stages that join estudiantes, tipos de pago y usuarios
# in a single round-trip to MongoDB. Used by list endpoints to avoid N+1.
_PAGO_HYDRATE_PIPELINE = [
    {
        "$lookup": {
            "from": "estudiantes",
            "localField": "id_estudiante",
            "foreignField": "id",
            "as": "_est",
        }
    },
    {
        "$lookup": {
            "from": "tipos_pagos",
            "localField": "id_tipo_pago",
            "foreignField": "id",
            "as": "_tp",
        }
    },
    {
        "$lookup": {
            "from": "usuarios",
            "localField": "created_by",
            "foreignField": "id",
            "as": "_cu",
        }
    },
    {
        "$lookup": {
            "from": "usuarios",
            "localField": "edited_by",
            "foreignField": "id",
            "as": "_eu",
        }
    },
    {
        "$lookup": {
            "from": "oficinas",
            "localField": "office_id",
            "foreignField": "id",
            "as": "_office",
        }
    },
    {
        "$addFields": {
            "estudiante_nombre": {"$arrayElemAt": ["$_est.nombre", 0]},
            "estudiante_ci": {"$arrayElemAt": ["$_est.ci", 0]},
            "estudiante_cu": {"$ifNull": [{"$arrayElemAt": ["$_est.cu", 0]}, ""]},
            "created_by_name": {"$arrayElemAt": ["$_cu.nombre", 0]},
            "edited_by_name": {"$arrayElemAt": ["$_eu.nombre", 0]},
            "office_nombre": {"$arrayElemAt": ["$_office.nombre", 0]},
            "suboficina": {"$arrayElemAt": ["$_office.suboficina", 0]},
            "items": {
                "$ifNull": [
                    "$items",
                    {
                        "$cond": [
                            {"$ifNull": ["$id_tipo_pago", False]},
                            [
                                {
                                    "id_tipo_pago": "$id_tipo_pago",
                                    "tipo_pago_nombre": {"$arrayElemAt": ["$_tp.nombre", 0]},
                                    "cantidad": "$cantidad",
                                    "monto": "$monto",
                                    "total": "$total",
                                }
                            ],
                            [],
                        ]
                    },
                ]
            },
            "prefijo_comprobante": {
                "$ifNull": [
                    "$prefijo_comprobante",
                    {"$arrayElemAt": ["$_office.prefijo_comprobante", 0]},
                ]
            },
            "comprobante_display": {
                "$concat": [
                    {
                        "$ifNull": [
                            "$prefijo_comprobante",
                            {"$arrayElemAt": ["$_office.prefijo_comprobante", 0]},
                        ]
                    },
                    "-",
                    "$cod_comprobante",
                    " / ",
                    {"$toString": "$gestion"},
                ]
            },
        }
    },
    {
        "$addFields": {
            "tipo_pago_nombre": {
                "$cond": [
                    {"$eq": [{"$size": "$items"}, 1]},
                    {"$arrayElemAt": ["$items.tipo_pago_nombre", 0]},
                    {
                        "$cond": [
                            {"$gt": [{"$size": "$items"}, 1]},
                            "Varios conceptos",
                            None,
                        ]
                    },
                ]
            },
            "id_tipo_pago": {"$arrayElemAt": ["$items.id_tipo_pago", 0]},
            "cantidad": {
                "$cond": [
                    {"$eq": [{"$size": "$items"}, 1]},
                    {"$arrayElemAt": ["$items.cantidad", 0]},
                    None,
                ]
            },
            "monto": {
                "$cond": [
                    {"$eq": [{"$size": "$items"}, 1]},
                    {"$arrayElemAt": ["$items.monto", 0]},
                    0,
                ]
            },
        }
    },
    {"$project": {"_id": 0, "_est": 0, "_tp": 0, "_cu": 0, "_eu": 0, "_office": 0}},
]


async def _pago_item_snapshot(
    office_id: str, id_tipo_pago: str, cantidad: float
) -> dict:
    tipo = await db.tipos_pagos.find_one(
        {"id": id_tipo_pago, "office_id": office_id}, {"_id": 0}
    )
    if not tipo:
        raise HTTPException(
            status_code=400, detail="Tipo de pago no encontrado en esta oficina."
        )
    monto = float(tipo["monto"])
    cantidad = float(cantidad)
    return {
        "id": str(uuid.uuid4()),
        "id_tipo_pago": id_tipo_pago,
        "tipo_pago_nombre": tipo["nombre"],
        "cantidad": cantidad,
        "monto": monto,
        "total": monto * cantidad,
    }


async def _hydrate_pago(pago: dict) -> dict:
    """Hydrate a receipt and normalize legacy one-item records for the UI."""
    office_id = pago["office_id"]
    estudiante = await db.estudiantes.find_one(
        {"id": pago["id_estudiante"], "office_id": office_id}, {"_id": 0}
    )
    office = await db.oficinas.find_one(
        {"id": office_id},
        {"_id": 0, "nombre": 1, "prefijo_comprobante": 1, "suboficina": 1},
    )
    pago["office_nombre"] = office["nombre"] if office else None
    pago["suboficina"] = office.get("suboficina", "") if office else ""
    pago["prefijo_comprobante"] = (
        pago.get("prefijo_comprobante")
        or (office.get("prefijo_comprobante") if office else None)
    )
    pago["comprobante_display"] = (
        format_receipt_display(
            pago["prefijo_comprobante"], pago["cod_comprobante"], pago["gestion"]
        )
        if pago.get("prefijo_comprobante")
        else None
    )
    pago["estudiante_nombre"] = estudiante["nombre"] if estudiante else None
    pago["estudiante_ci"] = estudiante["ci"] if estudiante else None
    pago["estudiante_cu"] = estudiante.get("cu", "") if estudiante else ""

    # Old receipts have a single concept on the receipt document itself.
    items = pago.get("items")
    if items is None:
        items = []
        if pago.get("id_tipo_pago"):
            tipo = await db.tipos_pagos.find_one(
                {"id": pago["id_tipo_pago"], "office_id": office_id}, {"_id": 0}
            )
            cantidad = float(pago.get("cantidad") or 0)
            monto = float(pago.get("monto") or 0)
            items.append(
                {
                    "id_tipo_pago": pago["id_tipo_pago"],
                    "tipo_pago_nombre": tipo["nombre"] if tipo else None,
                    "cantidad": cantidad,
                    "monto": monto,
                    "total": float(pago.get("total") or monto * cantidad),
                }
            )

    normalized_items = []
    for source_item in items:
        item = dict(source_item)
        if not item.get("tipo_pago_nombre"):
            tipo = await db.tipos_pagos.find_one(
                {"id": item.get("id_tipo_pago"), "office_id": office_id},
                {"_id": 0},
            )
            item["tipo_pago_nombre"] = tipo["nombre"] if tipo else None
        item["cantidad"] = float(item.get("cantidad") or 0)
        item["monto"] = float(item.get("monto") or 0)
        item["total"] = float(
            item.get("total")
            if item.get("total") is not None
            else item["cantidad"] * item["monto"]
        )
        normalized_items.append(item)

    pago["items"] = normalized_items
    pago["estado"] = pago.get("estado", "emitido")
    if normalized_items:
        pago["total"] = sum(item["total"] for item in normalized_items)
    else:
        pago["total"] = float(pago.get("total") or 0)

    if len(normalized_items) == 1:
        first = normalized_items[0]
        pago["id_tipo_pago"] = first["id_tipo_pago"]
        pago["tipo_pago_nombre"] = first.get("tipo_pago_nombre")
        pago["cantidad"] = first["cantidad"]
        pago["monto"] = first["monto"]
    elif len(normalized_items) > 1:
        pago["id_tipo_pago"] = None
        pago["tipo_pago_nombre"] = "Varios conceptos"
        pago["cantidad"] = None
        pago["monto"] = 0
    else:
        pago["id_tipo_pago"] = None
        pago["tipo_pago_nombre"] = None
        pago["cantidad"] = None
        pago["monto"] = 0

    if pago.get("created_by"):
        usuario = await db.usuarios.find_one({"id": pago["created_by"]}, {"_id": 0, "nombre": 1})
        pago["created_by_name"] = usuario["nombre"] if usuario else None
    if pago.get("edited_by"):
        usuario = await db.usuarios.find_one({"id": pago["edited_by"]}, {"_id": 0, "nombre": 1})
        pago["edited_by_name"] = usuario["nombre"] if usuario else None
    return pago


@api.post("/pagos", response_model=Pago, status_code=201)
async def create_pago(
    pago: PagoCreate, usuario: dict = Depends(require_roles("Administrador", "Caja"))
):
    office_id = await office_for_write(usuario, pago.office_id)
    estudiante = await db.estudiantes.find_one(
        {"id": pago.id_estudiante, "office_id": office_id}, {"_id": 0}
    )
    if not estudiante:
        raise HTTPException(status_code=400, detail="Estudiante no encontrado en esta oficina.")
    items = []
    estado = "borrador"
    if pago.id_tipo_pago:
        if pago.cantidad is None:
            raise HTTPException(status_code=400, detail="Indique la cantidad del concepto.")
        items.append(
            await _pago_item_snapshot(office_id, pago.id_tipo_pago, pago.cantidad)
        )
        estado = "emitido"

    gestion = datetime.now(timezone.utc).year
    office = await _office_exists(office_id, active=True)

    # atomic counter via counters collection
    contador = await db.contadores.find_one_and_update(
        {"_id": f"comprobante_{office_id}_{gestion}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = contador["seq"]
    codigo = f"{seq:05d}"

    doc = {
        "id": str(uuid.uuid4()),
        "cod_comprobante": codigo,
        "gestion": gestion,
        "prefijo_comprobante": office["prefijo_comprobante"],
        "items": items,
        "total": sum(item["total"] for item in items),
        "estado": estado,
        "fecha_pago": pago.fecha_pago,
        "office_id": office_id,
        "id_estudiante": pago.id_estudiante,
        "anulado": False,
        "anulado_at": None,
        "anulado_by": None,
        "created_at": iso(datetime.now(timezone.utc)),
        "created_by": usuario["id"],
    }
    # Keep the original fields for clients and documents that still expect
    # a single concept per receipt.
    if items:
        doc.update(
            {
                "id_tipo_pago": items[0]["id_tipo_pago"],
                "cantidad": items[0]["cantidad"],
                "monto": items[0]["monto"],
            }
        )
    await db.pagos.insert_one(doc)
    doc.pop("_id", None)
    doc = await _hydrate_pago(doc)
    return Pago(**doc)


@api.post("/pagos/{pago_id}/items", response_model=Pago)
async def add_pago_item(
    pago_id: str,
    body: PagoItemCreate,
    user: dict = Depends(require_roles("Administrador", "Caja")),
):
    scope = await office_scope(user)
    pago = await db.pagos.find_one({"id": pago_id, **scope}, {"_id": 0})
    if not pago:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado.")
    if pago.get("anulado") or pago.get("estado") != "borrador":
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden adicionar conceptos a un comprobante en borrador.",
        )

    item = await _pago_item_snapshot(
        pago["office_id"], body.id_tipo_pago, body.cantidad
    )
    now = iso(datetime.now(timezone.utc))
    update = {
        "$push": {"items": item},
        "$inc": {"total": item["total"]},
        "$set": {"edited_at": now, "edited_by": user["id"]},
    }
    if not pago.get("items"):
        update["$set"].update(
            {
                "id_tipo_pago": item["id_tipo_pago"],
                "cantidad": item["cantidad"],
                "monto": item["monto"],
            }
        )
    result = await db.pagos.update_one(
        {"id": pago_id, **scope, "estado": "borrador", "anulado": {"$ne": True}},
        update,
    )
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="El comprobante ya no está en borrador.")
    updated = await db.pagos.find_one({"id": pago_id}, {"_id": 0})
    return Pago(**await _hydrate_pago(updated))


@api.post("/pagos/{pago_id}/finalizar", response_model=Pago)
async def finalizar_pago(
    pago_id: str, user: dict = Depends(require_roles("Administrador", "Caja"))
):
    scope = await office_scope(user)
    pago = await db.pagos.find_one({"id": pago_id, **scope}, {"_id": 0})
    if not pago:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado.")
    if pago.get("anulado"):
        raise HTTPException(status_code=400, detail="El comprobante está anulado.")
    if pago.get("estado") != "borrador":
        raise HTTPException(status_code=400, detail="El comprobante ya fue emitido.")
    if not pago.get("items"):
        raise HTTPException(
            status_code=400, detail="Agregue al menos un concepto antes de emitir el comprobante."
        )
    await db.pagos.update_one(
        {"id": pago_id, **scope, "estado": "borrador"},
        {
            "$set": {
                "estado": "emitido",
                "edited_at": iso(datetime.now(timezone.utc)),
                "edited_by": user["id"],
            }
        },
    )
    updated = await db.pagos.find_one({"id": pago_id}, {"_id": 0})
    return Pago(**await _hydrate_pago(updated))


@api.delete("/pagos/{pago_id}/borrador")
async def delete_pago_draft(
    pago_id: str, user: dict = Depends(require_roles("Administrador", "Caja"))
):
    scope = await office_scope(user)
    pago = await db.pagos.find_one({"id": pago_id, **scope}, {"_id": 0})
    if not pago:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado.")
    if pago.get("estado") != "borrador":
        raise HTTPException(status_code=400, detail="Solo se pueden descartar borradores.")
    deleted = await db.pagos.delete_one(
        {"id": pago_id, **scope, "estado": "borrador"}
    )
    if not deleted.deleted_count:
        raise HTTPException(status_code=409, detail="El borrador ya no está disponible.")

    # Return the sequence only when this draft is still the latest allocation.
    # The compare-and-decrement shares the same atomic counter used by rentals,
    # so any newer payment/rental allocation makes this update miss instead of
    # rewinding past a number that may already be in flight.
    correlativo_reutilizado = False
    try:
        draft_seq = int(pago.get("cod_comprobante", ""))
        receipt_filter = {
            "office_id": pago["office_id"],
            "gestion": pago["gestion"],
            "cod_comprobante": pago["cod_comprobante"],
        }
        existing_payment = await db.pagos.find_one(
            {**receipt_filter, "id": {"$ne": pago_id}}, {"_id": 1}
        )
        existing_rental = await db.alquileres.find_one(
            {**receipt_filter, "estado": "pagado"}, {"_id": 1}
        )
        if draft_seq > 0 and not existing_payment and not existing_rental:
            counter_id = (
                f"comprobante_{pago['office_id']}_{pago['gestion']}"
            )
            counter_update = await db.contadores.update_one(
                {"_id": counter_id, "seq": draft_seq},
                {"$inc": {"seq": -1}},
            )
            correlativo_reutilizado = bool(counter_update.modified_count)
    except (KeyError, TypeError, ValueError):
        # Legacy drafts without a well-formed allocation cannot safely rewind.
        correlativo_reutilizado = False
    except Exception:
        logger.exception(
            "No se pudo devolver el correlativo del borrador descartado %s",
            pago_id,
        )
    return {"ok": True, "correlativo_reutilizado": correlativo_reutilizado}


@api.get("/pagos/{pago_id}", response_model=Pago)
async def get_pago(
    pago_id: str, user: dict = Depends(get_current_user)
):
    scope = await office_scope(user)
    pago = await db.pagos.find_one({"id": pago_id, **scope}, {"_id": 0})
    if not pago:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado.")
    return Pago(**await _hydrate_pago(pago))


@api.get("/pagos", response_model=PaginacionPagos)
async def get_pagos(
    q: Optional[str] = None,
    id_tipo_pago: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    incluir_anulados: bool = True,
    created_by: Optional[str] = None,
    office_id: Optional[str] = None,
    pag: int = Query(1, ge=1, description="Número de página"),
    tam: int = Query(20, ge=1, le=100, description="Elementos por página"),
    user: dict = Depends(get_current_user),
):
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=400,
            detail="La fecha inicial no puede ser posterior a la fecha final.",
        )

    scope = await office_scope(user, office_id)
    filt: dict = {**scope, "estado": {"$ne": "borrador"}}
    filter_clauses = []
    if not incluir_anulados:
        filt["anulado"] = False
    if id_tipo_pago:
        filter_clauses.append(
            {
                "$or": [
                    {"id_tipo_pago": id_tipo_pago},
                    {"items.id_tipo_pago": id_tipo_pago},
                ]
            }
        )
    if created_by:
        filt["created_by"] = created_by
    if fecha_desde or fecha_hasta:
        rng = {}
        if fecha_desde:
            rng["$gte"] = fecha_desde
        if fecha_hasta:
            rng["$lte"] = fecha_hasta
        filt["fecha_pago"] = rng

    # If q is present, filter by comprobante, estudiante or tipo de pago.
    ql = q.strip() if q else ""
    if ql:
        extra_or = []
        escaped_q = re.escape(ql)
        receipt_match = re.fullmatch(
            r"(?:(?P<prefix>[A-Za-z]{3})\s*-\s*)?"
            r"(?P<code>\d{1,5})(?:\s*/\s*(?P<year>\d{4}))?",
            ql,
        )
        if receipt_match:
            receipt_filter = {
                "cod_comprobante": receipt_match.group("code").zfill(5)
            }
            if receipt_match.group("year"):
                receipt_filter["gestion"] = int(receipt_match.group("year"))
            if receipt_match.group("prefix"):
                receipt_filter["prefijo_comprobante"] = receipt_match.group("prefix").upper()
            extra_or.append(receipt_filter)
        else:
            extra_or.append(
                {"cod_comprobante": {"$regex": escaped_q, "$options": "i"}}
            )
        # Match by estudiante: look up matching estudiantes ids
        est_ids = [
            e["id"]
            async for e in db.estudiantes.find(
                {
                    **scope,
                    "$or": [
                        {"nombre": {"$regex": escaped_q, "$options": "i"}},
                        {"ci": {"$regex": escaped_q, "$options": "i"}},
                        {"cu": {"$regex": escaped_q, "$options": "i"}},
                    ]
                },
                {"_id": 0, "id": 1},
            )
        ]
        if est_ids:
            extra_or.append({"id_estudiante": {"$in": est_ids}})
        tp_ids = [
            t["id"]
            async for t in db.tipos_pagos.find(
                {
                    **scope,
                    "nombre": {"$regex": escaped_q, "$options": "i"},
                },
                {"_id": 0, "id": 1},
            )
        ]
        if tp_ids:
            extra_or.extend(
                [
                    {"id_tipo_pago": {"$in": tp_ids}},
                    {"items.id_tipo_pago": {"$in": tp_ids}},
                ]
            )

        if extra_or:
            filter_clauses.append({"$or": extra_or})

    if filter_clauses:
        filt["$and"] = filter_clauses

    total_pagos = await db.pagos.count_documents(filt)
    total_paginas = (total_pagos + tam - 1) // tam if total_pagos > 0 else 1
    salto = (pag - 1) * tam

    cursor = db.pagos.aggregate(
        [
            {"$match": filt},
            {"$sort": {"created_at": -1}},
            {"$skip": salto},
            {"$limit": tam},
            *_PAGO_HYDRATE_PIPELINE,
        ]
    )
    pagos = [Pago(**p) async for p in cursor]
    return {
        "items": pagos,
        "total": total_pagos,
        "page": pag,
        "size": tam,
        "pages": total_paginas,
    }

@api.get("/comprobantes")
async def buscar_comprobantes(
    q: Optional[str] = None,
    id_tipo_pago: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    created_by: Optional[str] = None,
    office_id: Optional[str] = None,
    pag: int = Query(1, ge=1),
    tam: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(status_code=400, detail="La fecha inicial no puede ser posterior a la fecha final.")
    for value in (fecha_desde, fecha_hasta):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise HTTPException(status_code=400, detail="Fecha inválida. Use YYYY-MM-DD.")
    scope = await office_scope(user, office_id)
    students = {**scope, "estado": {"$ne": "borrador"}}
    rentals = {
        **scope,
        "estado": {"$in": ["pagado", "cancelado"]},
        "cod_comprobante": {"$type": "string", "$ne": ""},
    }
    if fecha_desde or fecha_hasta:
        dates = {}
        if fecha_desde:
            dates["$gte"] = fecha_desde
        if fecha_hasta:
            # Rental payment timestamps are ISO datetimes, student dates are YYYY-MM-DD.
            dates["$lt"] = (date.fromisoformat(fecha_hasta) + timedelta(days=1)).isoformat()
        students["fecha_pago"] = dates
        rentals["fecha_pago"] = dates
    if created_by:
        students["created_by"] = created_by
        rentals["paid_by"] = created_by
    if id_tipo_pago:
        students["$and"] = [{"$or": [
            {"id_tipo_pago": id_tipo_pago}, {"items.id_tipo_pago": id_tipo_pago},
        ]}]
        # Student payment concepts do not apply to room rentals.
        rentals["id"] = {"$exists": False}
    term = q.strip() if q else ""
    if term:
        escaped = re.escape(term)
        receipt = re.fullmatch(
            r"(?:(?P<prefix>[A-Za-z]{3})\s*-\s*)?"
            r"(?P<code>\d{1,5})(?:\s*/\s*(?P<year>\d{4}))?", term,
        )
        if receipt:
            code = {"cod_comprobante": receipt["code"].zfill(5)}
            if receipt["year"]:
                code["gestion"] = int(receipt["year"])
            if receipt["prefix"]:
                code["prefijo_comprobante"] = receipt["prefix"].upper()
            student_or, rental_or = [code], [code]
        else:
            student_or = [{"cod_comprobante": {"$regex": escaped, "$options": "i"}}]
            rental_or = [{"cod_comprobante": {"$regex": escaped, "$options": "i"}}]
        est_ids = [e["id"] async for e in db.estudiantes.find(
            {**scope, "$or": [
                {"nombre": {"$regex": escaped, "$options": "i"}},
                {"ci": {"$regex": escaped, "$options": "i"}},
                {"cu": {"$regex": escaped, "$options": "i"}},
            ]}, {"_id": 0, "id": 1},
        )]
        if est_ids:
            student_or.append({"id_estudiante": {"$in": est_ids}})
        tp_ids = [t["id"] async for t in db.tipos_pagos.find(
            {**scope, "nombre": {"$regex": escaped, "$options": "i"}},
            {"_id": 0, "id": 1},
        )]
        if tp_ids:
            student_or.extend([
                {"id_tipo_pago": {"$in": tp_ids}},
                {"items.id_tipo_pago": {"$in": tp_ids}},
            ])
        rental_or.extend([
            {"cliente_nombre": {"$regex": escaped, "$options": "i"}},
            {"cliente_ci": {"$regex": escaped, "$options": "i"}},
            {"cliente_cu": {"$regex": escaped, "$options": "i"}},
            {"ambiente_nombre": {"$regex": escaped, "$options": "i"}},
            {"tarifa_nombre": {"$regex": escaped, "$options": "i"}},
        ])
        students.setdefault("$and", []).append({"$or": student_or})
        rentals.setdefault("$and", []).append({"$or": rental_or})
    pipeline = [
        {"$match": students},
        *_PAGO_HYDRATE_PIPELINE,
        {"$addFields": {"origen": "estudiantil"}},
        {"$unionWith": {"coll": "alquileres", "pipeline": [
            {"$match": rentals},
            {"$lookup": {
                "from": "oficinas",
                "localField": "office_id",
                "foreignField": "id",
                "as": "_office",
            }},
            {"$addFields": {
                "suboficina": {
                    "$ifNull": [{"$arrayElemAt": ["$_office.suboficina", 0]}, ""]
                }
            }},
            {"$project": {"_id": 0, "intervals": 0, "_office": 0}},
            {"$addFields": {"origen": "alquiler"}},
        ]}},
        {"$facet": {
            "count": [{"$count": "total"}],
            "items": [
                {"$sort": {"fecha_pago": -1, "id": 1}},
                {"$skip": (pag - 1) * tam},
                {"$limit": tam},
            ],
        }},
    ]
    result = (await db.pagos.aggregate(pipeline).to_list(1))[0]
    total = result["count"][0]["total"] if result["count"] else 0
    return {"items": result["items"], "total": total, "page": pag, "size": tam,
            "pages": (total + tam - 1) // tam if total else 1}
@api.put("/pagos/{pago_id}", response_model=Pago)
async def update_pago(
    pago_id: str, body: PagoCreate, user: dict = Depends(require_roles("Administrador", "Caja"))
):
    scope = await office_scope(user)
    pago = await db.pagos.find_one({"id": pago_id, **scope}, {"_id": 0})
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    if pago.get("anulado"):
        raise HTTPException(
            status_code=400, detail="No se puede editar un pago anulado"
        )
    stored_items = pago.get("items")
    if isinstance(stored_items, list) and len(stored_items) > 1:
        raise HTTPException(
            status_code=400,
            detail="No se puede editar desde esta pantalla un comprobante con varios conceptos.",
        )
    if pago.get("estado") == "borrador":
        raise HTTPException(status_code=400, detail="No se puede editar un borrador desde esta pantalla.")
    if body.office_id and body.office_id != pago["office_id"]:
        raise HTTPException(status_code=400, detail="No se puede cambiar la oficina de un pago.")

    update: dict = {}

    if body.id_estudiante and body.id_estudiante != pago["id_estudiante"]:
        if not await db.estudiantes.find_one(
            {"id": body.id_estudiante, "office_id": pago["office_id"]}
        ):
            raise HTTPException(status_code=400, detail="Estudiante no encontrado en esta oficina")
        update["id_estudiante"] = body.id_estudiante

    itemized = isinstance(stored_items, list) and len(stored_items) == 1
    current_item = stored_items[0] if itemized else {}
    current_type_id = current_item.get("id_tipo_pago") or pago.get("id_tipo_pago")
    new_monto = float(current_item.get("monto", pago.get("monto", 0)) or 0)
    if body.id_tipo_pago and body.id_tipo_pago != current_type_id:
        tp = await db.tipos_pagos.find_one(
            {"id": body.id_tipo_pago, "office_id": pago["office_id"]}, {"_id": 0}
        )
        if not tp:
            raise HTTPException(status_code=400, detail="Tipo de pago no encontrado en esta oficina")
        update["id_tipo_pago"] = body.id_tipo_pago
        new_monto = float(tp["monto"])
        update["monto"] = new_monto
        if itemized:
            update["items.0.id_tipo_pago"] = body.id_tipo_pago
            update["items.0.tipo_pago_nombre"] = tp["nombre"]
            update["items.0.monto"] = new_monto

    current_cantidad = float(current_item.get("cantidad", pago.get("cantidad", 0)) or 0)
    new_cantidad = current_cantidad
    if body.cantidad is not None and body.cantidad != current_cantidad:
        update["cantidad"] = float(body.cantidad)
        new_cantidad = float(body.cantidad)
        if itemized:
            update["items.0.cantidad"] = new_cantidad

    # if monto or cantidad changed → recompute total
    if "monto" in update or "cantidad" in update:
        update["total"] = float(new_monto) * float(new_cantidad)
        if itemized:
            update["items.0.total"] = update["total"]

    if body.fecha_pago and body.fecha_pago != pago["fecha_pago"]:
        update["fecha_pago"] = body.fecha_pago

    if not update:
        raise HTTPException(status_code=400, detail="Sin cambios")

    update["edited_at"] = iso(datetime.now(timezone.utc))
    update["edited_by"] = user["id"]

    await db.pagos.update_one({"id": pago_id, **scope}, {"$set": update})
    p = await db.pagos.find_one({"id": pago_id}, {"_id": 0})
    p = await _hydrate_pago(p)
    return Pago(**p)


@api.post("/pagos/{pago_id}/anular")
async def anular_pago(
    pago_id: str,
    usuario: dict = Depends(require_roles("Administrador", "Caja")),
):
    scope = await office_scope(usuario)
    pago = await db.pagos.find_one({"id": pago_id, **scope})
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado.")
    if pago.get("anulado"):
        raise HTTPException(status_code=400, detail="El pago ya está anulado.")
    if usuario.get("rol") == "Caja":
        if pago.get("created_by") != usuario.get("id"):
            raise HTTPException(
                status_code=403,
                detail="Caja solo puede anular sus propios comprobantes.",
            )
        if _printed_payment_date(pago.get("fecha_pago")) != _current_bolivia_date():
            raise HTTPException(
                status_code=403,
                detail="Caja solo puede anular sus comprobantes el día de la fecha impresa.",
            )

    annul_filter = {
        "id": pago_id,
        **scope,
        "anulado": {"$ne": True},
    }
    if usuario.get("rol") == "Caja":
        annul_filter.update(
            {
                "created_by": usuario["id"],
                "fecha_pago": pago.get("fecha_pago"),
            }
        )
    result = await db.pagos.update_one(
        annul_filter,
        {
            "$set": {
                "anulado": True,
                "anulado_at": iso(datetime.now(timezone.utc)),
                "anulado_by": usuario["id"],
            }
        },
    )
    if not result.modified_count:
        raise HTTPException(
            status_code=409,
            detail="El comprobante cambió de estado; vuelva a consultarlo.",
        )
    return {"ok": True}


# ----------------------------- Reportes -----------------------------
def _periodo_to_range(periodo: str, desde: Optional[str], hasta: Optional[str]):
    today = date.today()
    if periodo == "diario":
        d = today.isoformat()
        return d, d
    if periodo == "semanal":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start.isoformat(), end.isoformat()
    if periodo == "mensual":
        start = today.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1)
        else:
            next_month = start.replace(month=start.month + 1)
        end = next_month - timedelta(days=1)
        return start.isoformat(), end.isoformat()
    if periodo == "rango":
        if not desde or not hasta:
            raise HTTPException(
                status_code=400, detail="Se requieren fechas desde y hasta"
            )
        return desde, hasta
    raise HTTPException(status_code=400, detail="Periodo inválido")


@api.get("/reportes")
async def reportes(
    periodo: Literal["diario", "semanal", "mensual", "rango"] = "diario",
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    created_by: Optional[str] = None,
    office_id: Optional[str] = None,
    user: dict = Depends(require_roles("Administrador")),
):
    d, h = _periodo_to_range(periodo, desde, hasta)
    try:
        start_date, end_date = date.fromisoformat(d), date.fromisoformat(h)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida. Use YYYY-MM-DD.")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="La fecha inicial no puede ser posterior a la fecha final.")
    scope = await office_scope(user, office_id)
    filt = {
        **scope,
        "fecha_pago": {"$gte": d, "$lte": h},
        "estado": {"$ne": "borrador"},
    }
    if created_by:
        filt["created_by"] = created_by
    cursor = db.pagos.aggregate(
        [
            {"$match": filt},
            {"$sort": {"fecha_pago": 1}},
            *_PAGO_HYDRATE_PIPELINE,
        ]
    )
    pagos: List[dict] = [p async for p in cursor]

    validos = [p for p in pagos if not p.get("anulado")]
    anulados = [p for p in pagos if p.get("anulado")]
    rental_filter = {**scope, "estado": "pagado",
                     "fecha_pago": {"$gte": d, "$lt": (end_date + timedelta(days=1)).isoformat()}}
    if created_by:
        rental_filter["paid_by"] = created_by
    alquileres = await db.alquileres.find(
        rental_filter, {"_id": 0, "intervals": 0}
    ).sort("fecha_pago", 1).to_list(None)
    total_estudiantil = sum(float(p["total"]) for p in validos)
    total_alquileres = sum(float(a["total"]) for a in alquileres)
    total_validos = total_estudiantil + total_alquileres
    total_anulados = sum(float(p["total"]) for p in anulados)
    selected_office = (
        await db.oficinas.find_one({"id": scope["office_id"]}, {"_id": 0, "nombre": 1})
        if scope.get("office_id") else None
    )
    return {
        "desde": d,
        "hasta": h,
        "office_id": scope.get("office_id"),
        "office_nombre": selected_office["nombre"] if selected_office else "Todas las oficinas",
        "pagos": pagos,
        "alquileres": alquileres,
        "totales": {
            "validos": total_validos,
            "estudiantiles": total_estudiantil,
            "alquileres": total_alquileres,
            "anulados": total_anulados,
            "diferencia": total_validos - total_anulados,
            "count_validos": len(validos) + len(alquileres),
            "count_anulados": len(anulados),
        },
    }


@api.get("/dashboard/stats")
async def dashboard_stats(
    office_id: Optional[str] = None, user: dict = Depends(get_current_user)
):
    scope = await office_scope(user, office_id)
    today = date.today().isoformat()
    estudiantes_count = await db.estudiantes.count_documents(scope)
    tipospagos_count = await db.tipos_pagos.count_documents(scope)
    pagos_hoy_count = await db.pagos.count_documents(
        {
            **scope,
            "fecha_pago": today,
            "anulado": False,
            "estado": {"$ne": "borrador"},
        }
    )
    agg = db.pagos.aggregate(
        [
            {
                "$match": {
                    **scope,
                    "fecha_pago": today,
                    "anulado": False,
                    "estado": {"$ne": "borrador"},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$total"}}},
        ]
    )
    monto_hoy = 0.0
    async for row in agg:
        monto_hoy = float(row.get("total", 0))
    selected_office = (
        await db.oficinas.find_one({"id": scope["office_id"]}, {"_id": 0, "nombre": 1})
        if scope.get("office_id") else None
    )
    return {
        "estudiantes": estudiantes_count,
        "tipospagos": tipospagos_count,
        "pagos_hoy": pagos_hoy_count,
        "monto_hoy": monto_hoy,
        "office_id": scope.get("office_id"),
        "office_nombre": selected_office["nombre"] if selected_office else "Todas las oficinas",
        "institucion": {
            "linea1": "Universidad Mayor, Real y Pontificia de San Francisco Xavier",
            "linea2": selected_office["nombre"] if selected_office else "Todas las oficinas",
            "linea3": "Administración",
        },
    }


# ----------------------------- Startup seed -----------------------------
def _new_office_prefix(nombre: str, used: set) -> str:
    letters = re.sub(r"[^A-Z]", "", str(nombre or "").upper())
    base = (letters + "XXX")[:3]
    if base not in used:
        return base
    for candidate in itertools.product(string.ascii_uppercase, repeat=3):
        prefix = "".join(candidate)
        if prefix not in used:
            return prefix
    raise RuntimeError("No quedan prefijos de comprobante disponibles.")


async def ensure_office_receipt_prefixes():
    offices = await db.oficinas.find({}, {"_id": 0, "id": 1, "nombre": 1, "prefijo_comprobante": 1}) \
        .sort([("created_at", 1), ("id", 1)]).to_list(None)
    used = set()
    for office in offices:
        current = office.get("prefijo_comprobante")
        prefix = current.strip().upper() if isinstance(current, str) else ""
        if not re.fullmatch(r"[A-Z]{3}", prefix) or prefix in used:
            prefix = _new_office_prefix(office.get("nombre", ""), used)
            await db.oficinas.update_one(
                {"id": office["id"]}, {"$set": {"prefijo_comprobante": prefix}}
            )
        used.add(prefix)
        await db.pagos.update_many(
            {
                "office_id": office["id"],
                "$or": [
                    {"prefijo_comprobante": {"$exists": False}},
                    {"prefijo_comprobante": None},
                    {"prefijo_comprobante": ""},
                ],
            },
            {"$set": {"prefijo_comprobante": prefix}},
        )


async def reconcile_payment_counters():
    """Migrate legacy counters and raise scoped counters to receipt maxima."""
    counters = await db.contadores.find(
        {"_id": {"$regex": "^comprobante_"}}
    ).to_list(None)
    legacy_counters = []
    for counter in counters:
        legacy_year = counter.get("_id", "").removeprefix("comprobante_")
        try:
            legacy_seq = int(counter.get("seq", 0) or 0)
        except (TypeError, ValueError):
            continue
        if legacy_year.isdigit() and legacy_seq > 0:
            legacy_counters.append((int(legacy_year), legacy_seq))

    if legacy_counters:
        offices = await db.oficinas.find({}, {"_id": 0, "id": 1}).to_list(None)
        for gestion, legacy_seq in legacy_counters:
            for office in offices:
                counter_id = f"comprobante_{office['id']}_{gestion}"
                await db.contadores.update_one(
                    {"_id": counter_id},
                    {"$max": {"seq": legacy_seq}},
                    upsert=True,
                )
        # Include newly initialized office-scoped counters in the usual
        # reconciliation against extant student-payment and rental receipts.
        counters = await db.contadores.find(
            {"_id": {"$regex": "^comprobante_"}}
        ).to_list(None)

    for counter in counters:
        counter_id = counter.get("_id", "")
        suffix = counter_id.removeprefix("comprobante_")
        office_id, separator, year_text = suffix.rpartition("_")
        if not separator or not office_id or not year_text.isdigit():
            continue

        gestion = int(year_text)
        highest_rows = await db.pagos.aggregate(
            [
                {"$match": {"office_id": office_id, "gestion": gestion}},
                {
                    "$addFields": {
                        "_receipt_seq": {
                            "$convert": {
                                "input": "$cod_comprobante",
                                "to": "int",
                                "onError": 0,
                                "onNull": 0,
                            }
                        }
                    }
                },
                {"$group": {"_id": None, "seq": {"$max": "$_receipt_seq"}}},
            ]
        ).to_list(1)
        highest_existing = int(highest_rows[0]["seq"]) if highest_rows else 0
        rental_rows = await db.alquileres.aggregate(
            [
                {"$match": {"office_id": office_id, "gestion": gestion, "estado": "pagado"}},
                {"$addFields": {"_receipt_seq": {"$convert": {"input": "$cod_comprobante", "to": "int", "onError": 0, "onNull": 0}}}},
                {"$group": {"_id": None, "seq": {"$max": "$_receipt_seq"}}},
            ]
        ).to_list(1)
        highest_existing = max(highest_existing, int(rental_rows[0]["seq"]) if rental_rows else 0)
        current_seq = int(counter.get("seq", 0) or 0)
        if current_seq >= highest_existing:
            continue

        result = await db.contadores.update_one(
            {
                "_id": counter_id,
                "seq": {"$eq": counter.get("seq"), "$lt": highest_existing},
            },
            {"$set": {"seq": highest_existing}},
        )
        if result.modified_count:
            logger.info(
                "Correlativo de comprobantes reconciliado para oficina %s, gestión %s.",
                office_id,
                gestion,
            )


@app.on_event("startup")
async def startup():
    await ensure_office_receipt_prefixes()
    await db.oficinas.create_index("id", unique=True)
    await db.oficinas.create_index("nombre_key", unique=True)
    await db.oficinas.create_index("prefijo_comprobante", unique=True)
    await db.usuarios.create_index("email", unique=True)
    await db.usuarios.create_index("id", unique=True)
    await db.usuarios.create_index(
        [("office_id", 1), ("rol", 1)],
        unique=True,
        partialFilterExpression={"office_id": {"$type": "string"}, "rol": "Administrador"},
        name="one_admin_per_office",
    )
    await db.estudiantes.create_index("id", unique=True)
    await db.estudiantes.create_index("ci")
    await db.estudiantes.create_index("office_id")
    duplicate_personas = await db.personas.aggregate(
        [
            {"$group": {"_id": "$ci_key", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$limit": 1},
        ]
    ).to_list(1)
    if duplicate_personas:
        raise RuntimeError(
            "No se puede unificar Personas: hay C.I. duplicados entre oficinas. "
            "Consolide esos registros antes de iniciar la aplicación."
        )
    persona_indexes = await db.personas.index_information()
    if "person_ci_per_office" in persona_indexes:
        await db.personas.drop_index("person_ci_per_office")
    await db.personas.update_many(
        {},
        {"$unset": {"office_id": "", "office_nombre": ""}},
    )
    await db.personas.create_index("id", unique=True)
    await db.personas.create_index(
        "ci_key", unique=True, name="person_ci_global"
    )
    await db.estudiantes.create_index(
        [("office_id", 1), ("cu", 1)],
        unique=True,
        partialFilterExpression={"office_id": {"$type": "string"}, "cu": {"$gt": ""}},
        name="student_cu_per_office",
    )
    await db.tipos_pagos.create_index("id", unique=True)
    await db.tipos_pagos.create_index(
        [("office_id", 1), ("nombre_key", 1)],
        unique=True,
        partialFilterExpression={"office_id": {"$type": "string"}, "nombre_key": {"$type": "string"}},
        name="type_name_per_office",
    )
    await db.ambientes.create_index("id", unique=True)
    await db.ambientes.create_index(
        [("office_id", 1), ("nombre_key", 1)],
        unique=True,
        partialFilterExpression={
            "office_id": {"$type": "string"},
            "nombre_key": {"$type": "string"},
        },
        name="ambiente_name_per_office",
    )
    await db.tarifas_ambientes.create_index("id", unique=True)
    await db.tarifas_ambientes.create_index([("office_id", 1), ("ambiente_id", 1)])
    await db.alquileres.create_index("id", unique=True)
    await db.alquileres.create_index(
        [("office_id", 1), ("gestion", 1), ("cod_comprobante", 1)],
        unique=True,
        partialFilterExpression={"estado": "pagado"},
        name="rental_receipt_per_office_year",
    )
    await db.alquileres.create_index([("ambiente_id", 1), ("fecha", 1), ("estado", 1)])
    # MongoDB creates a unique _id index automatically for every collection.
    await reconcile_rental_occupancy()
    await db.pagos.create_index([("office_id", 1), ("gestion", 1), ("cod_comprobante", 1)],
                                unique=True,
                                partialFilterExpression={"office_id": {"$type": "string"}},
                                name="receipt_per_office_year")
    await db.pagos.create_index([("office_id", 1), ("fecha_pago", 1)])
    await db.pagos.create_index("fecha_pago")
    await db.pagos.create_index("created_by")
    await db.pagos.create_index("id_estudiante")
    await db.pagos.create_index("id_tipo_pago")
    await reconcile_payment_counters()

    admin = await db.usuarios.find_one({"email": SUPER_ADMIN_EMAIL})
    if admin is None:
        await db.usuarios.insert_one(
            {
                "id": str(uuid.uuid4()),
                "email": SUPER_ADMIN_EMAIL,
                "nombre": ADMIN_NAME,
                "rol": SUPER_ADMIN_ROLE,
                "office_id": None,
                "password_hash": hash_password(ADMIN_PASSWORD),
                "created_at": iso(datetime.now(timezone.utc)),
            }
        )
        logger.info("Creación de cuenta Super Admin.")
    else:
        updates = {}
        if not verify_password(ADMIN_PASSWORD, admin["password_hash"]):
            updates["password_hash"] = hash_password(ADMIN_PASSWORD)
        if admin.get("nombre") != ADMIN_NAME:
            updates["nombre"] = ADMIN_NAME
        if admin.get("rol") != SUPER_ADMIN_ROLE:
            updates["rol"] = SUPER_ADMIN_ROLE
        if admin.get("office_id") is not None:
            updates["office_id"] = None
        if updates:
            await db.usuarios.update_one(
                {"_id": admin["_id"]},
                {"$set": updates},
            )
            logger.info("Configuración de cuenta Super Admin actualizada.")


@app.on_event("shutdown")
async def shutdown():
    client.close()


@api.get("/")
async def root():
    return {"ok": True, "service": "Comprobantes USFX"}

@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        # Esto atrapará CUALQUIER error interno y obligará a enviar los headers de CORS
        print(f"❌ ERROR CRÍTICO DETECTADO: {str(exc)}")

        # Obtenemos el origen de la petición del frontend
        origin = request.headers.get("origin", "*")

        return JSONResponse(
            status_code=500,
            content={"detail": f"Error interno en el servidor: {str(exc)}"},
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
            },
        )


cors_origins_raw = os.getenv("CORS_ORIGINS", "*")
origins = cors_origins_raw.split(",") if cors_origins_raw else []


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(api)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
