import os
import logging
import bcrypt
import jwt
import uuid
from jwt.exceptions import InvalidTokenError
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from motor.motor_asyncio import AsyncIOMotorClient
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
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
ADMIN_NAME = os.environ["ADMIN_NAME"]

# ----------------------------- DB -----------------------------
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ----------------------------- APP -----------------------------
app = FastAPI(title="Comprobantes USFX")
api = APIRouter(prefix="/api")
# Security
security = HTTPBearer()

ROLES = ("Administrador", "Caja", "Consultas")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("comprobantes")

# ----------------------------- MODELS -----------------------------
class UserPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: EmailStr
    nombre: str
    rol: Literal["Administrador", "Caja", "Consultas"]
    created_at: Optional[str] = None

class UserCreate(BaseModel):
    email: EmailStr
    nombre: str
    password_hash: str = Field(min_length=4)
    rol: Literal["Administrador", "Caja", "Consultas"]

class UserUpdate(BaseModel):
    nombre: Optional[str] = None
    rol: Optional[Literal["Administrador", "Caja", "Consultas"]] = None
    password_hash: Optional[str] = Field(default=None, min_length=4)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    token: str
    usuario: UserPublic

class Estudiante(BaseModel):    
    ci: str
    cu: Optional[str] = ""
    nombre: str
    gestion: int

class EstudianteCreate(Estudiante):
    pass

class EstudianteOut(Estudiante):
    id: str
    created_at: Optional[str] = None

class TipoPago(BaseModel):    
    nombre: str
    monto: float
    descripcion: Optional[str] = ""
    inicio: str  # ISO date YYYY-MM-DD
    fin: Optional[str] = None

class TipoPagoCreate(TipoPago):
    pass

class TipoPagoOut(TipoPago):
    id: str
    created_at: Optional[str] = None

class PagoCreate(BaseModel):
    id_estudiante: str
    id_tipopago: str
    cantidad: float = Field(gt=0)
    fecha_pago: str  # YYYY-MM-DD

class PagoOut(BaseModel):
    id: str
    codcomprobante: str
    gestion: int
    cantidad: float
    monto: float
    total: float
    fecha_pago: str
    id_estudiante: str
    id_tipopago: str
    estudiante_nombre: Optional[str] = None
    estudiante_ci: Optional[str] = None
    estudiante_cu: Optional[str] = ""
    tipopago_nombre: Optional[str] = None
    anulado: bool = False
    anulado_at: Optional[str] = None
    anulado_by: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    edited_at: Optional[str] = None
    edited_by: Optional[str] = None
    edited_by_name: Optional[str] = None

class PagoUpdate(BaseModel):
    id_estudiante: Optional[str] = None
    id_tipopago: Optional[str] = None
    cantidad: Optional[float] = Field(default=None, gt=0)
    fecha_pago: Optional[str] = None

# ----------------------------- HELPERS -----------------------------
def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRES_MIN),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")        
        email = payload.get("email")        
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido.")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")
    
    user = await db.usuarios.find_one({"email": email}, {"_id": 0})
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado.")
    return user

def require_roles(*allowed: str):
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in allowed:
            raise HTTPException(status_code=403, detail="Sin permisos para esta acción.")
        return user

    return _dep

# ----------------------------- AUTH ENDPOINTS -----------------------------
@api.post("/auth/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(body: LoginRequest, response: Response):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email},{"_id": 0})
    # Evitar revelar si el usuario existe o no
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas."
        )

    # Verificar contraseña
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas."
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
        "user": {
            "id": user["id"],
            "email": user["email"],
            "nombre": user["nombre"],
            "rol": user["rol"],
        },
    }

@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}

@api.get("/auth/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return UserPublic(**user)

# ----------------------------- Users CRUD (admin) -----------------------------
@api.get("/users", response_model=List[UserPublic])
async def list_users(_: dict = Depends(require_roles("Administrador"))):
    cursor = db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
    return [UserPublic(**u) async for u in cursor]

@api.get("/users/list")
async def list_users_minimal(_: dict = Depends(get_current_user)):
    """Lista mínima de usuarios (id, name, role) — disponible a todos los autenticados
    para alimentar el filtro 'Registrado por' en búsqueda y reportes."""
    cursor = db.users.find({}, {"_id": 0, "id": 1, "name": 1, "role": 1}).sort("name", 1)
    return [u async for u in cursor]

@api.post("/users", response_model=UserPublic, status_code=201)
async def create_user(body: UserCreate, _: dict = Depends(require_roles("admin"))):
    email = body.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "nombre": body.nombre,
        "rol": body.rol,
        "password_hash": hash_password(body.password),
        "created_at": iso(datetime.now(timezone.utc)),
    }
    await db.users.insert_one(doc)
    return UserPublic(id=doc["id"], email=doc["email"], name=doc["nombre"], role=doc["rol"], created_at=doc["created_at"])

@api.put("/users/{user_id}", response_model=UserPublic)
async def update_user(user_id: str, body: UserUpdate, _: dict = Depends(require_roles("Administrador"))):
    update = {}
    if body.name is not None:
        update["name"] = body.name
    if body.role is not None:
        update["role"] = body.role
    if body.password:
        update["password_hash"] = hash_password(body.password)
    if not update:
        raise HTTPException(status_code=400, detail="Sin cambios")
    res = await db.users.update_one({"id": user_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return UserPublic(**u)

@api.delete("/users/{user_id}")
async def delete_user(user_id: str, current: dict = Depends(require_roles("Administrador"))):
    if user_id == current["id"]:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if target.get("email") == ADMIN_EMAIL:
        raise HTTPException(status_code=400, detail="No puedes eliminar el admin principal")
    await db.users.delete_one({"id": user_id})
    return {"ok": True}

# ----------------------------- CRUD Estudiantes -----------------------------
@api.get("/estudiantes", response_model=List[EstudianteOut])
async def list_estudiantes(q: Optional[str] = None, _: dict = Depends(get_current_user)):    
    filt = {}
    if q:
        filt = {
            "$or": [                
                {"ci": {"$regex": q, "$options": "i"}},
                {"cu": {"$regex": q, "$options": "i"}},
                {"nombre": {"$regex": q, "$options": "i"}},
            ]
        }
    cursor = db.estudiantes.find(filt, {"_id": 0}).sort("nombre", 1).limit(500)
    return [EstudianteOut(**e) async for e in cursor]

@api.post("/estudiantes", response_model=EstudianteOut, status_code=201)
async def create_estudiante(estudiante: EstudianteCreate, _: dict = Depends(require_roles("Administrador", "Caja"))):    
    if await db.estudiantes.find_one({"cu": estudiante.cu}):
        raise HTTPException(status_code=400, detail="El CU ya existe")
    doc = estudiante.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = iso(datetime.now(timezone.utc))
    await db.estudiantes.insert_one(doc)
    return EstudianteOut(**{k: v for k, v in doc.items() if k != "_id"})

@api.put("/estudiantes/{est_id}", response_model=EstudianteOut)
async def update_estudiante(est_id: str, estudiante: EstudianteCreate, _: dict = Depends(require_roles("Administrador"))):    
    otro = await db.estudiantes.find_one({"cu": estudiante.cu, "id": {"$ne": est_id}})
    if otro:
        raise HTTPException(status_code=400, detail="El estudiante ya existe")
    res = await db.estudiantes.update_one({"id": est_id}, {"$set": estudiante.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    e = await db.estudiantes.find_one({"id": est_id}, {"_id": 0})
    return EstudianteOut(**e)

@api.delete("/estudiantes/{est_id}")
async def delete_estudiante(est_id: str, _: dict = Depends(require_roles("Administrador"))):    
    if await db.pagos.find_one({"id_estudiante": est_id}):
        raise HTTPException(status_code=400, detail="No se puede eliminar: tiene pagos registrados")
    res = await db.estudiantes.delete_one({"id": est_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return {"ok": True}

# ----------------------------- CRUD TiposPagos -----------------------------
@api.get("/tipos-pagos", response_model=List[TipoPagoOut])
async def list_tipospagos(activos: Optional[bool] = False, _: dict = Depends(get_current_user)):
    filt = {}
    if activos:
        today = date.today().isoformat()
        filt = {
            "inicio": {"$lte": today},
            "$or": [{"fin": None}, {"fin": {"$gte": today}}, {"fin": ""}],
        }
    cursor = db.tipospagos.find(filt, {"_id": 0}).sort("nombre", 1)
    return [TipoPagoOut(**t) async for t in cursor]

@api.post("/tipos-pagos", response_model=TipoPagoOut, status_code=201)
async def create_tipopago(tipo: TipoPagoCreate, _: dict = Depends(require_roles("Administrador"))):
    if await db.tipospagos.find_one({"nombre": tipo.nombre}):
        raise HTTPException(status_code=400, detail="El tipo de pago ya existe")
    doc = tipo.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = iso(datetime.now(timezone.utc))
    await db.tipospagos.insert_one(doc)
    return TipoPagoOut(**{k: v for k, v in doc.items() if k != "_id"})

@api.put("/tipos-pagos/{tip_id}", response_model=TipoPagoOut)
async def update_tipopago(tip_id: str, tipo: TipoPagoCreate, _: dict = Depends(require_roles("Administrador"))):
    otro = await db.tipospagos.find_one({"nombre": tipo.nombre, "id": {"$ne": tip_id}})
    if otro:
        raise HTTPException(status_code=400, detail="El tipo de pago ya existe")
    res = await db.tipospagos.update_one({"id": tip_id}, {"$set": tipo.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado")
    t = await db.tipospagos.find_one({"id": tip_id}, {"_id": 0})
    return TipoPagoOut(**t)

@api.delete("/tipos-pagos/{tip_id}")
async def delete_tipopago(tip_id: str, _: dict = Depends(require_roles("Administrador"))):
    if await db.tipospagos.find_one({"id_tipopago": tip_id}):
        raise HTTPException(status_code=400, detail="No se puede eliminar: tiene pagos asociados")
    res = await db.tipospagos.delete_one({"id": tip_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado")
    return {"ok": True}

# ----------------------------- Pagos: comprobante preview -----------------------------
@api.get("/pagos/preview-comprobante")
async def preview_comprobante(_: dict = Depends(require_roles("admin", "caja"))):
    gestion = datetime.now(timezone.utc).year
    # Find max codcomprobante for this gestion
    last = (
        await db.pagos.find({"gestion": gestion}, {"_id": 0, "codcomprobante": 1})
        .sort("codcomprobante", -1)
        .to_list(1)
    )
    next_num = 1
    if last:
        try:
            next_num = int(last[0]["codcomprobante"]) + 1
        except Exception:
            next_num = 1
    cod = f"{next_num:05d}"
    return {"codcomprobante": cod, "gestion": gestion, "display": f"{cod}/{gestion}"}


# ----------------------------- Pagos CRUD -----------------------------
# Aggregation pipeline stages that join estudiantes / tipospagos / users
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
            "from": "tipospagos",
            "localField": "id_tipopago",
            "foreignField": "id",
            "as": "_tp",
        }
    },
    {
        "$lookup": {
            "from": "users",
            "localField": "created_by",
            "foreignField": "id",
            "as": "_cu",
        }
    },
    {
        "$lookup": {
            "from": "users",
            "localField": "edited_by",
            "foreignField": "id",
            "as": "_eu",
        }
    },
    {
        "$addFields": {
            "estudiante_nombre": {"$arrayElemAt": ["$_est.nombre", 0]},
            "estudiante_ci": {"$arrayElemAt": ["$_est.ci", 0]},
            "estudiante_cu": {
                "$ifNull": [{"$arrayElemAt": ["$_est.cu", 0]}, ""]
            },
            "tipopago_nombre": {"$arrayElemAt": ["$_tp.nombre", 0]},
            "created_by_name": {"$arrayElemAt": ["$_cu.name", 0]},
            "edited_by_name": {"$arrayElemAt": ["$_eu.name", 0]},
        }
    },
    {"$project": {"_id": 0, "_est": 0, "_tp": 0, "_cu": 0, "_eu": 0}},
]


async def _hydrate_pago(p: dict) -> dict:
    """Single-doc hydration — used by POST/PUT responses where only one
    pago is returned. List endpoints use the aggregation pipeline instead."""
    est = await db.estudiantes.find_one({"id": p["id_estudiante"]}, {"_id": 0})
    tp = await db.tipospagos.find_one({"id": p["id_tipopago"]}, {"_id": 0})
    p["estudiante_nombre"] = est["nombre"] if est else None
    p["estudiante_ci"] = est["ci"] if est else None
    p["estudiante_cu"] = est.get("cu", "") if est else ""
    p["tipopago_nombre"] = tp["nombre"] if tp else None
    if p.get("created_by"):
        u = await db.users.find_one({"id": p["created_by"]}, {"_id": 0, "name": 1})
        p["created_by_name"] = u["name"] if u else None
    if p.get("edited_by"):
        u = await db.users.find_one({"id": p["edited_by"]}, {"_id": 0, "name": 1})
        p["edited_by_name"] = u["name"] if u else None
    return p


@api.post("/pagos", response_model=PagoOut, status_code=201)
async def create_pago(body: PagoCreate, user: dict = Depends(require_roles("admin", "caja"))):
    est = await db.estudiantes.find_one({"id": body.id_estudiante}, {"_id": 0})
    if not est:
        raise HTTPException(status_code=400, detail="Estudiante no encontrado")
    tp = await db.tipospagos.find_one({"id": body.id_tipopago}, {"_id": 0})
    if not tp:
        raise HTTPException(status_code=400, detail="Tipo de pago no encontrado")

    gestion = datetime.now(timezone.utc).year

    # atomic counter via counters collection
    counter = await db.counters.find_one_and_update(
        {"_id": f"comprobante_{gestion}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    if counter is None:
        # depending on driver version - read again
        counter = await db.counters.find_one({"_id": f"comprobante_{gestion}"})
    seq = counter["seq"] if counter else 1
    cod = f"{seq:05d}"

    monto = float(tp["monto"])
    total = monto * float(body.cantidad)

    doc = {
        "id": str(uuid.uuid4()),
        "codcomprobante": cod,
        "gestion": gestion,
        "cantidad": float(body.cantidad),
        "monto": monto,
        "total": total,
        "fecha_pago": body.fecha_pago,
        "id_estudiante": body.id_estudiante,
        "id_tipopago": body.id_tipopago,
        "anulado": False,
        "anulado_at": None,
        "anulado_by": None,
        "created_at": iso(datetime.now(timezone.utc)),
        "created_by": user["id"],
    }
    await db.pagos.insert_one(doc)
    doc.pop("_id", None)
    doc = await _hydrate_pago(doc)
    return PagoOut(**doc)


@api.get("/pagos", response_model=List[PagoOut])
async def list_pagos(
    q: Optional[str] = None,
    id_tipopago: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    incluir_anulados: bool = True,
    created_by: Optional[str] = None,
    _: dict = Depends(get_current_user),
):
    filt: dict = {}
    if not incluir_anulados:
        filt["anulado"] = False
    if id_tipopago:
        filt["id_tipopago"] = id_tipopago
    if created_by:
        filt["created_by"] = created_by
    if fecha_desde or fecha_hasta:
        rng = {}
        if fecha_desde:
            rng["$gte"] = fecha_desde
        if fecha_hasta:
            rng["$lte"] = fecha_hasta
        filt["fecha_pago"] = rng

    # If q present, we need to filter by codcomprobante (cod/gestion) or estudiante name
    extra_or = []
    if q:
        ql = q.strip()
        if "/" in ql:
            try:
                cod_part, ges_part = ql.split("/", 1)
                extra_or.append({"codcomprobante": cod_part.zfill(5), "gestion": int(ges_part)})
            except Exception:
                pass
        extra_or.append({"codcomprobante": {"$regex": ql, "$options": "i"}})
        # Match by estudiante: look up matching estudiantes ids
        est_ids = [
            e["id"]
            async for e in db.estudiantes.find(
                {
                    "$or": [
                        {"nombre": {"$regex": ql, "$options": "i"}},
                        {"ci": {"$regex": ql, "$options": "i"}},
                        {"cu": {"$regex": ql, "$options": "i"}},
                    ]
                },
                {"_id": 0, "id": 1},
            )
        ]
        if est_ids:
            extra_or.append({"id_estudiante": {"$in": est_ids}})
        tp_ids = [
            t["id"]
            async for t in db.tipospagos.find(
                {"nombre": {"$regex": ql, "$options": "i"}}, {"_id": 0, "id": 1}
            )
        ]
        if tp_ids:
            extra_or.append({"id_tipopago": {"$in": tp_ids}})

        filt["$or"] = extra_or

    cursor = db.pagos.aggregate(
        [
            {"$match": filt},
            {"$sort": {"created_at": -1}},
            {"$limit": 1000},
            *_PAGO_HYDRATE_PIPELINE,
        ]
    )
    return [PagoOut(**p) async for p in cursor]


@api.put("/pagos/{pago_id}", response_model=PagoOut)
async def update_pago(pago_id: str, body: PagoUpdate, user: dict = Depends(require_roles("admin"))):
    pago = await db.pagos.find_one({"id": pago_id}, {"_id": 0})
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    if pago.get("anulado"):
        raise HTTPException(status_code=400, detail="No se puede editar un pago anulado")

    update: dict = {}

    if body.id_estudiante and body.id_estudiante != pago["id_estudiante"]:
        if not await db.estudiantes.find_one({"id": body.id_estudiante}):
            raise HTTPException(status_code=400, detail="Estudiante no encontrado")
        update["id_estudiante"] = body.id_estudiante

    new_monto = pago["monto"]
    if body.id_tipopago and body.id_tipopago != pago["id_tipopago"]:
        tp = await db.tipospagos.find_one({"id": body.id_tipopago}, {"_id": 0})
        if not tp:
            raise HTTPException(status_code=400, detail="Tipo de pago no encontrado")
        update["id_tipopago"] = body.id_tipopago
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

    await db.pagos.update_one({"id": pago_id}, {"$set": update})
    p = await db.pagos.find_one({"id": pago_id}, {"_id": 0})
    p = await _hydrate_pago(p)
    return PagoOut(**p)


@api.post("/pagos/{pago_id}/anular")
async def anular_pago(pago_id: str, user: dict = Depends(require_roles("admin"))):
    pago = await db.pagos.find_one({"id": pago_id})
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    if pago.get("anulado"):
        raise HTTPException(status_code=400, detail="El pago ya está anulado")
    await db.pagos.update_one(
        {"id": pago_id},
        {
            "$set": {
                "anulado": True,
                "anulado_at": iso(datetime.now(timezone.utc)),
                "anulado_by": user["id"],
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
            raise HTTPException(status_code=400, detail="Se requieren fechas desde y hasta")
        return desde, hasta
    raise HTTPException(status_code=400, detail="Periodo inválido")


@api.get("/reportes")
async def reportes(
    periodo: Literal["diario", "semanal", "mensual", "rango"] = "diario",
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    created_by: Optional[str] = None,
    _: dict = Depends(require_roles("admin")),
):
    d, h = _periodo_to_range(periodo, desde, hasta)
    filt = {"fecha_pago": {"$gte": d, "$lte": h}}
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
    return {
        "desde": d,
        "hasta": h,
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
async def dashboard_stats(user: dict = Depends(get_current_user)):
    today = date.today().isoformat()
    estudiantes_count = await db.estudiantes.count_documents({})
    tipospagos_count = await db.tipospagos.count_documents({})
    pagos_hoy_count = await db.pagos.count_documents({"fecha_pago": today, "anulado": False})
    agg = db.pagos.aggregate(
        [
            {"$match": {"fecha_pago": today, "anulado": False}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}},
        ]
    )
    monto_hoy = 0.0
    async for row in agg:
        monto_hoy = float(row.get("total", 0))
    return {
        "estudiantes": estudiantes_count,
        "tipospagos": tipospagos_count,
        "pagos_hoy": pagos_hoy_count,
        "monto_hoy": monto_hoy,
        "institucion": {
            "linea1": "Universidad Mayor, Real y Pontificia de San Francisco Xavier",
            "linea2": "Facultad de Medicina",
            "linea3": "Administración",
        },
    }


# ----------------------------- Startup seed -----------------------------
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    # `id` indexes — used by $lookup foreignField joins in /api/pagos and /api/reportes
    await db.users.create_index("id", unique=True)
    await db.estudiantes.create_index("id", unique=True)
    await db.estudiantes.create_index("codigo", unique=True)
    await db.estudiantes.create_index("ci")
    await db.tipospagos.create_index("id", unique=True)
    await db.tipospagos.create_index("codigo", unique=True)
    await db.pagos.create_index([("gestion", 1), ("codcomprobante", 1)])
    await db.pagos.create_index("fecha_pago")
    # filter indexes used by /api/pagos
    await db.pagos.create_index("created_by")
    await db.pagos.create_index("id_estudiante")
    await db.pagos.create_index("id_tipopago")

    admin = await db.usuarios.find_one({"email": ADMIN_EMAIL.lower()})
    if admin is None:
        await db.usuarios.insert_one(
            {
                "id": str(uuid.uuid4()),
                "email": ADMIN_EMAIL.lower(),
                "name": ADMIN_NAME,
                "role": "admin",
                "password_hash": hash_password(ADMIN_PASSWORD),
                "created_at": iso(datetime.now(timezone.utc)),
            }
        )
        logger.info(f"Seeded admin: {ADMIN_EMAIL}")
    else:
        if not verify_password(ADMIN_PASSWORD, admin["password_hash"]):
            await db.usuarios.update_one(
                {"email": ADMIN_EMAIL.lower()},
                {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}},
            )
            logger.info("Updated admin password to match .env")


@app.on_event("shutdown")
async def shutdown():
    client.close()


@api.get("/")
async def root():
    return {"ok": True, "service": "Comprobantes USFX"}


app.include_router(api)

# CORS
origins = os.environ.get("CORS_ORIGINS", "*")
allow_origins = [o.strip() for o in origins.split(",")] if origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
