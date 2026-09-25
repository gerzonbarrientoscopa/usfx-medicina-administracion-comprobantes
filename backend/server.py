import os
import logging
import re
import itertools
import string
import bcrypt
import jwt
import uuid
from jwt.exceptions import InvalidTokenError
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Query, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
from typing import List, Optional, Literal


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
app = FastAPI(title="Comprobantes USFX")
api = APIRouter(prefix="/api")
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

class PagoBase(BaseModel):
    id_estudiante: str
    id_tipo_pago: str
    cantidad: float = Field(gt=0)
    fecha_pago: str  # YYYY-MM-DD
    office_id: Optional[str] = None
    office_nombre: Optional[str] = None

class PagoCreate(PagoBase):
    pass


class Pago(PagoBase):
    id: str
    cod_comprobante: str
    gestion: int    
    monto: float
    total: float    
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
    for collection in (db.usuarios, db.estudiantes, db.tipos_pagos, db.pagos):
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
    if await db.pagos.find_one({"id_tipo_pago": tipo_id, "office_id": target["office_id"]}):
        raise HTTPException(status_code=400, detail="No se puede eliminar: tiene pagos registrados.")
    await db.tipos_pagos.delete_one({"id": tipo_id, **scope})
    return {"ok": True}


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
            "tipo_pago_nombre": {"$arrayElemAt": ["$_tp.nombre", 0]},
            "created_by_name": {"$arrayElemAt": ["$_cu.nombre", 0]},
            "edited_by_name": {"$arrayElemAt": ["$_eu.nombre", 0]},
            "office_nombre": {"$arrayElemAt": ["$_office.nombre", 0]},
            "suboficina": {"$arrayElemAt": ["$_office.suboficina", 0]},
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
    {"$project": {"_id": 0, "_est": 0, "_tp": 0, "_cu": 0, "_eu": 0, "_office": 0}},
]


async def _hydrate_pago(pago: dict) -> dict:
    """Single-doc hydration — used by POST/PUT responses where only one
    pago is returned. List endpoints use the aggregation pipeline instead."""
    office_id = pago["office_id"]
    estudiante = await db.estudiantes.find_one(
        {"id": pago["id_estudiante"], "office_id": office_id}, {"_id": 0}
    )
    tipo = await db.tipos_pagos.find_one(
        {"id": pago["id_tipo_pago"], "office_id": office_id}, {"_id": 0}
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
    pago["tipo_pago_nombre"] = tipo["nombre"] if tipo else None
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
    tipo = await db.tipos_pagos.find_one(
        {"id": pago.id_tipo_pago, "office_id": office_id}, {"_id": 0}
    )
    if not tipo:
        raise HTTPException(status_code=400, detail="Tipo de pago no encontrado en esta oficina.")

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

    monto = float(tipo["monto"])
    total = monto * float(pago.cantidad)

    doc = {
        "id": str(uuid.uuid4()),
        "cod_comprobante": codigo,
        "gestion": gestion,
        "prefijo_comprobante": office["prefijo_comprobante"],
        "cantidad": float(pago.cantidad),
        "monto": monto,
        "total": total,
        "fecha_pago": pago.fecha_pago,
        "office_id": office_id,
        "id_estudiante": pago.id_estudiante,
        "id_tipo_pago": pago.id_tipo_pago,
        "anulado": False,
        "anulado_at": None,
        "anulado_by": None,
        "created_at": iso(datetime.now(timezone.utc)),
        "created_by": usuario["id"],
    }
    await db.pagos.insert_one(doc)
    doc.pop("_id", None)
    doc = await _hydrate_pago(doc)
    return Pago(**doc)


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
    filt: dict = scope.copy()
    if not incluir_anulados:
        filt["anulado"] = False
    if id_tipo_pago:
        filt["id_tipo_pago"] = id_tipo_pago
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
            extra_or.append({"id_tipo_pago": {"$in": tp_ids}})

        filt["$or"] = extra_or

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
    if body.office_id and body.office_id != pago["office_id"]:
        raise HTTPException(status_code=400, detail="No se puede cambiar la oficina de un pago.")

    update: dict = {}

    if body.id_estudiante and body.id_estudiante != pago["id_estudiante"]:
        if not await db.estudiantes.find_one(
            {"id": body.id_estudiante, "office_id": pago["office_id"]}
        ):
            raise HTTPException(status_code=400, detail="Estudiante no encontrado en esta oficina")
        update["id_estudiante"] = body.id_estudiante

    new_monto = pago["monto"]
    if body.id_tipo_pago and body.id_tipo_pago != pago["id_tipo_pago"]:
        tp = await db.tipos_pagos.find_one(
            {"id": body.id_tipo_pago, "office_id": pago["office_id"]}, {"_id": 0}
        )
        if not tp:
            raise HTTPException(status_code=400, detail="Tipo de pago no encontrado en esta oficina")
        update["id_tipo_pago"] = body.id_tipo_pago
        new_monto = float(tp["monto"])
        update["monto"] = new_monto

    new_cantidad = pago["cantidad"]
    if body.cantidad is not None and body.cantidad != pago["cantidad"]:
        update["cantidad"] = float(body.cantidad)
        new_cantidad = float(body.cantidad)

    # if monto or cantidad changed → recompute total
    if "monto" in update or "cantidad" in update:
        update["total"] = float(new_monto) * float(new_cantidad)

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
async def anular_pago(pago_id: str, usuario: dict = Depends(require_roles("Administrador"))):
    scope = await office_scope(usuario)
    pago = await db.pagos.find_one({"id": pago_id, **scope})
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado.")
    if pago.get("anulado"):
        raise HTTPException(status_code=400, detail="El pago ya está anulado.")
    await db.pagos.update_one(
        {"id": pago_id, **scope},
        {
            "$set": {
                "anulado": True,
                "anulado_at": iso(datetime.now(timezone.utc)),
                "anulado_by": usuario["id"],
            }
        },
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
    scope = await office_scope(user, office_id)
    filt = {**scope, "fecha_pago": {"$gte": d, "$lte": h}}
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
    total_validos = sum(float(p["total"]) for p in validos)
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
        "totales": {
            "validos": total_validos,
            "anulados": total_anulados,
            "diferencia": total_validos - total_anulados,
            "count_validos": len(validos),
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
        {**scope, "fecha_pago": today, "anulado": False}
    )
    agg = db.pagos.aggregate(
        [
            {"$match": {**scope, "fecha_pago": today, "anulado": False}},
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
    await db.pagos.create_index([("office_id", 1), ("gestion", 1), ("cod_comprobante", 1)],
                                unique=True,
                                partialFilterExpression={"office_id": {"$type": "string"}},
                                name="receipt_per_office_year")
    await db.pagos.create_index([("office_id", 1), ("fecha_pago", 1)])
    await db.pagos.create_index("fecha_pago")
    await db.pagos.create_index("created_by")
    await db.pagos.create_index("id_estudiante")
    await db.pagos.create_index("id_tipo_pago")

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
