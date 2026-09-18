import os
import logging
import bcrypt
import jwt
import uuid
from jwt.exceptions import InvalidTokenError
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Query, Depends, Request, Response, status
from fastapi.responses import JSONResponse
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
    password: str = Field(min_length=4)
    rol: Literal["Administrador", "Caja", "Consultas"]


class UserUpdate(BaseModel):
    nombre: Optional[str] = None
    rol: Optional[Literal["Administrador", "Caja", "Consultas"]] = None
    password: Optional[str] = Field(default=None, min_length=4)

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

class PagoCreate(PagoBase):
    pass


class Pago(PagoBase):
    id: str
    cod_comprobante: str
    gestion: int    
    monto: float
    total: float    
    estudiante_nombre: Optional[str] = None
    estudiante_ci: Optional[str] = None
    estudiante_cu: Optional[str] = ""
    tipo_pago_nombre: Optional[str] = None
    anulado: bool = False
    anulado_at: Optional[str] = None
    anulado_by: Optional[str] = None
    creado_at: Optional[str] = None
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
        if user.get("rol") not in allowed:
            raise HTTPException(
                status_code=403, detail="Sin permisos para esta acción."
            )
        return user

    return _dep


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
        "usuario": {
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
@api.get("/usuarios", response_model=UserPaginationResponse)
async def get_users(
    pag: int = Query(1, ge=1, description="Número de página"),
    tam: int = Query(10, ge=1, le=100, description="Elementos por página"),
    _: dict = Depends(require_roles("Administrador"))
):
    # 1. Calcular el salto (offset)
    salto = (pag - 1) * tam
    
    # 2. Contar de manera eficiente el total de documentos en la colección
    total_usuarios = await db.usuarios.count_documents({})
    
    # 3. Consultar solo el bloque/lote de datos requerido
    cursor = db.usuarios.find({}, {"_id": 0, "password_hash": 0}) \
                        .sort([("nombre", 1), ("email", 1)]) \
                        .skip(salto) \
                        .limit(tam)
    
    # 4. Traer el lote a memoria de manera veloz con to_list()
    usuarios_dict = await cursor.to_list(length=tam)
    
    # 5. Mapear los diccionarios al modelo UserPublic de forma síncrona
    usuarios_validados = [UserPublic(**u) for u in usuarios_dict]
    
    # 6. Calcular el número total de páginas (redondeo hacia arriba)
    total_paginas = (total_usuarios + tam - 1) // tam if total_usuarios > 0 else 1
    
    # 7. Retornar la estructura exacta que pide UserPaginationResponse
    return {
        "items": usuarios_validados,
        "total": total_usuarios,
        "page": pag,
        "size": tam,
        "pages": total_paginas
    }    

@api.get("/usuarios/list")
async def get_users_minimal(_: dict = Depends(get_current_user)):
    """Lista mínima de usuarios (id, name, role) — disponible a todos los autenticados
    para alimentar el filtro 'Registrado por' en búsqueda y reportes."""
    cursor = db.usuarios.find({}, {"_id": 0, "id": 1, "nombre": 1, "rol": 1}).sort(
        "nombre", 1
    )
    
    return [u async for u in cursor]


@api.post("/usuarios", response_model=UserPublic, status_code=201)
async def create_user(usuario: UserCreate, _: dict = Depends(require_roles("Administrador"))):
    email = usuario.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="El email ya está registrado.")    
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "nombre": usuario.nombre,
        "rol": usuario.rol,
        "password_hash": hash_password(usuario.password),
        "created_at": iso(datetime.now(timezone.utc)),
    }
    await db.usuarios.insert_one(doc)
    return UserPublic(
        id=doc["id"],
        email=doc["email"],
        nombre=doc["nombre"],
        rol=doc["rol"],
        created_at=doc["created_at"],
    )


@api.put("/usuarios/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: str, usuario: UserUpdate, _: dict = Depends(require_roles("Administrador"))
):
    update = {}
    if usuario.nombre is not None:
        update["nombre"] = usuario.nombre
    if usuario.rol is not None:
        update["rol"] = usuario.rol
    if usuario.password:
        update["password_hash"] = hash_password(usuario.password)
    if not update:
        raise HTTPException(status_code=400, detail="Sin cambios.")
    res = await db.usuarios.update_one({"id": user_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    userUpdate = await db.usuarios.find_one(
        {"id": user_id}, {"_id": 0, "password_hash": 0}
    )
    return UserPublic(**userUpdate)


@api.delete("/usuarios/{user_id}")
async def delete_user(
    user_id: str, current: dict = Depends(require_roles("Administrador"))
):
    if user_id == current["id"]:
        raise HTTPException(
            status_code=400, detail="No puedes eliminar tu propio usuario."
        )
    target = await db.usuarios.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if target.get("email") == ADMIN_EMAIL:
        raise HTTPException(
            status_code=400, detail="No puedes eliminar el admin principal."
        )
    await db.usuarios.delete_one({"id": user_id})
    return {"ok": True}
    # return {"message": "Usuario eliminado."}


# ----------------------------- CRUD Estudiantes -----------------------------
@api.get("/estudiantes", response_model=PaginacionEstudiantes)
async def get_estudiantes(
    pag: int = Query(1, ge=1, description="Número de página"),
    tam: int = Query(10, ge=1, le=100, description="Elementos por página"),
    textoBuscar: Optional[str] = None, _: dict = Depends(get_current_user)
):    
    filt = {}
    if textoBuscar:
        filt = {
            "$or": [
                {"ci": {"$regex": textoBuscar, "$options": "i"}},
                {"cu": {"$regex": textoBuscar, "$options": "i"}},
                {"nombre": {"$regex": textoBuscar, "$options": "i"}},
            ]
        }

    # 1. Calcular el salto (offset)
    salto = (pag - 1) * tam
    
    # 2. Contar de manera eficiente el total de documentos en la colección
    total_estudiantes = await db.estudiantes.count_documents(filt)
    
    # 3. Consultar solo el bloque/lote de datos requerido
    cursor = db.estudiantes.find(filt, {"_id": 0}) \
                        .sort([("nombre", 1), ("cu", 1)]) \
                        .skip(salto) \
                        .limit(tam)
    
    # 4. Traer el lote a memoria de manera veloz con to_list()
    estudiantes_dict = await cursor.to_list(length=tam)
    
    # 5. Mapear los diccionarios al modelo UserPublic de forma síncrona
    estudiantes_validados = [Estudiante(**u) for u in estudiantes_dict]
    
    # 6. Calcular el número total de páginas (redondeo hacia arriba)
    total_paginas = (total_estudiantes + tam - 1) // tam if total_estudiantes > 0 else 1
    
    # 7. Retornar la estructura exacta que pide UserPaginationResponse
    return {
        "items": estudiantes_validados,
        "total": total_estudiantes,
        "page": pag,
        "size": tam,
        "pages": total_paginas
    }    
    estudiantes = await db.estudiantes.find(filt, {"_id": 0}).sort("nombre", 1).to_list(500)        
    return estudiantes


@api.post("/estudiantes", response_model=Estudiante, status_code=201)
async def create_estudiante(
    estudiante: EstudianteCreate,
    _: dict = Depends(require_roles("Administrador", "Caja")),
):
    existing = await db.estudiantes.find_one({"cu": estudiante.cu})
    if existing:
        raise HTTPException(status_code=400, detail="El estudiante ya existe.")    
    estudiante_dict = estudiante.model_dump()
    estudiante_dict["id"] = str(uuid.uuid4())    
    await db.estudiantes.insert_one(estudiante_dict)
    return Estudiante(**estudiante_dict)            


@api.put("/estudiantes/{est_id}", response_model=Estudiante)
async def update_estudiante(
    est_id: str,
    estudiante: EstudianteCreate,
    _: dict = Depends(require_roles("Administrador")),
):
    otroEstudiante = await db.estudiantes.find_one({"cu": estudiante.cu, "id": {"$ne": est_id}})
    if otroEstudiante:
        raise HTTPException(status_code=400, detail="El estudiante ya existe.")
    update = {}
    if estudiante.ci is not None:
        update["ci"] = estudiante.ci
    if estudiante.cu is not None:
        update["cu"] = estudiante.cu
    if estudiante.nombre is not None:
        update["nombre"] = estudiante.nombre
    if estudiante.gestion is not None:
        update["gestion"] = estudiante.gestion    
    if not update:
        raise HTTPException(status_code=400, detail="Sin cambios.")   
    res = await db.estudiantes.update_one({"id": est_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    estudianteUpdate = await db.estudiantes.find_one({"id": est_id}, {"_id": 0})
    return Estudiante(**estudianteUpdate)    


@api.delete("/estudiantes/{est_id}")
async def delete_estudiante(
    est_id: str, _: dict = Depends(require_roles("Administrador"))
):
    target = await db.estudiantes.find_one({"id": est_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")    
    if await db.pagos.find_one({"id_estudiante": est_id}):
        raise HTTPException(
            status_code=400, detail="No se puede eliminar: tiene pagos registrados."
        )
    await db.estudiantes.delete_one({"id": est_id})
    return {"ok": True}        


# ----------------------------- CRUD TiposPagos -----------------------------
@api.get("/tipos-pagos", response_model=PaginacionTiposPagos)
async def get_tipos_pagos(
    pag: int = Query(1, ge=1, description="Número de página"),
    tam: int = Query(10, ge=1, le=100, description="Elementos por página"),
    activos: Optional[bool] = False, _: dict = Depends(get_current_user)
):
    filt = {}
    if activos:
        today = date.today().isoformat()
        filt = {
            "inicio": {"$lte": today},
            "$or": [{"fin": None}, {"fin": {"$gte": today}}, {"fin": ""}],
        }

    # 1. Calcular el salto (offset)
    salto = (pag - 1) * tam
    
    # 2. Contar de manera eficiente el total de documentos en la colección
    total_tipos = await db.usuarios.count_documents({})
    
    # 3. Consultar solo el bloque/lote de datos requerido
    cursor = db.tipos_pagos.find({}, {"_id": 0}) \
                        .sort([("nombre", 1), ("inicio", -1)]) \
                        .skip(salto) \
                        .limit(tam)
    
    # 4. Traer el lote a memoria de manera veloz con to_list()
    tipos_dict = await cursor.to_list(length=tam)
    
    # 5. Mapear los diccionarios al modelo UserPublic de forma síncrona
    tipos_validados = [TipoPago(**t) for t in tipos_dict]
    
    # 6. Calcular el número total de páginas (redondeo hacia arriba)
    total_paginas = (total_tipos + tam - 1) // tam if total_tipos > 0 else 1
    
    # 7. Retornar la estructura exacta que pide UserPaginationResponse
    return {
        "items": tipos_validados,
        "total": total_tipos,
        "page": pag,
        "size": tam,
        "pages": total_paginas
    }    
    tipos = await db.tipos_pagos.find(filt, {"_id": 0}).sort("nombre", 1).to_list(1000)
    return tipos    


@api.post("/tipos-pagos", response_model=TipoPago, status_code=201)
async def create_tipo_pago(
    tipo: TipoPagoCreate, _: dict = Depends(require_roles("Administrador"))
):
    existing = await db.tipos_pagos.find_one({"nombre": tipo.nombre})
    if existing:
        raise HTTPException(status_code=400, detail="El tipo de pago ya existe.")    
    tipo_dict = tipo.model_dump()
    tipo_dict["id"] = str(uuid.uuid4())    
    await db.tipos_pagos.insert_one(tipo_dict)
    return TipoPago(**tipo_dict)    


@api.put("/tipos-pagos/{tipo_id}", response_model=TipoPago)
async def update_tipopago(
    tipo_id: str, tipo: TipoPagoCreate, _: dict = Depends(require_roles("Administrador"))
):
    otroTipoPago = await db.tipos_pagos.find_one({"nombre": tipo.nombre, "id": {"$ne": tipo_id}})
    if otroTipoPago:
        raise HTTPException(status_code=400, detail="El tipo de pago ya existe.")
    update = {}
    if tipo.nombre is not None:
        update["nombre"] = tipo.nombre
    if tipo.monto is not None:
        update["monto"] = tipo.monto
    if tipo.descripcion is not None:
        update["descripcion"] = tipo.descripcion
    if tipo.inicio is not None:
        update["inicio"] = tipo.inicio
    if tipo.fin is not None:
        update["fin"] = tipo.fin
    if not update:
        raise HTTPException(status_code=400, detail="Sin cambios.")   
    res = await db.tipos_pagos.update_one({"id": tipo_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado.")
    tipoUpdate = await db.tipos_pagos.find_one({"id": tipo_id}, {"_id": 0})
    return TipoPago(**tipoUpdate)


@api.delete("/tipos-pagos/{tipo_id}")
async def delete_tipo_pago(
    tipo_id: str, _: dict = Depends(require_roles("Administrador"))
):
    target = await db.tipos_pagos.find_one({"id": tipo_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado.")    
    await db.tipos_pagos.delete_one({"id": tipo_id})
    return {"ok": True}


# ----------------------------- Pagos: comprobante preview -----------------------------
@api.get("/pagos/preview-comprobante")
async def preview_comprobante(_: dict = Depends(require_roles("Administrador", "Caja"))):
    gestion = datetime.now(timezone.utc).year
    # Buscar max cod_comprobante por gestion
    ultimoPago = (
        await db.pagos.find({"gestion": gestion}, {"_id": 0, "cod_comprobante": 1})
        .sort("cod_comprobante", -1)
        .to_list(1)
    )
    siguiente_num = 1
    if ultimoPago:
        try:
            siguiente_num = int(ultimoPago[0]["cod_comprobante"]) + 1
        except Exception:
            siguiente_num = 1
    codigo = f"{siguiente_num:05d}"
    return {"cod_comprobante": codigo, "gestion": gestion, "display": f"{codigo}/{gestion}"}


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
            "from": "tipos_pagos",
            "localField": "id_tipo_pago",
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
            "estudiante_cu": {"$ifNull": [{"$arrayElemAt": ["$_est.cu", 0]}, ""]},
            "tipopago_nombre": {"$arrayElemAt": ["$_tp.nombre", 0]},
            "created_by_name": {"$arrayElemAt": ["$_cu.name", 0]},
            "edited_by_name": {"$arrayElemAt": ["$_eu.name", 0]},
        }
    },
    {"$project": {"_id": 0, "_est": 0, "_tp": 0, "_cu": 0, "_eu": 0}},
]


async def _hydrate_pago(pago: dict) -> dict:
    """Single-doc hydration — used by POST/PUT responses where only one
    pago is returned. List endpoints use the aggregation pipeline instead."""
    estudiante = await db.estudiantes.find_one({"id": pago["id_estudiante"]}, {"_id": 0})
    tipo = await db.tipos_pagos.find_one({"id": pago["id_tipo_pago"]}, {"_id": 0})
    pago["estudiante_nombre"] = estudiante["nombre"] if estudiante else None
    pago["estudiante_ci"] = estudiante["ci"] if estudiante else None
    pago["estudiante_cu"] = estudiante.get("cu", "") if estudiante else ""
    pago["tipo_pago_nombre"] = tipo["nombre"] if tipo else None
    if pago.get("created_by"):
        usuario = await db.usuarios.find_one({"id": pago["created_by"]}, {"_id": 0, "name": 1})
        pago["created_by_name"] = usuario["nombre"] if usuario else None
    if pago.get("edited_by"):
        usuario = await db.usuarios.find_one({"id": pago["edited_by"]}, {"_id": 0, "name": 1})
        pago["edited_by_name"] = usuario["nombre"] if usuario else None
    return pago


@api.post("/pagos", response_model=Pago, status_code=201)
async def create_pago(
    pago: PagoCreate, usuario: dict = Depends(require_roles("Administrador", "Caja"))
):
    estudiante = await db.estudiantes.find_one({"id": pago.id_estudiante}, {"_id": 0})
    if not estudiante:
        raise HTTPException(status_code=400, detail="Estudiante no encontrado.")
    tipo = await db.tipos_pagos.find_one({"id": pago.id_tipo_pago}, {"_id": 0})
    if not tipo:
        raise HTTPException(status_code=400, detail="Tipo de pago no encontrado.")

    gestion = datetime.now(timezone.utc).year

    # atomic counter via counters collection
    contador = await db.contadores.find_one_and_update(
        {"_id": f"comprobante_{gestion}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    if contador is None:        
        contador = await db.contadores.find_one({"_id": f"comprobante_{gestion}"})
    seq = contador["seq"] if contador else 1
    codigo = f"{seq:05d}"

    monto = float(tipo["monto"])
    total = monto * float(pago.cantidad)

    doc = {
        "id": str(uuid.uuid4()),
        "cod_comprobante": codigo,
        "gestion": gestion,
        "cantidad": float(pago.cantidad),
        "monto": monto,
        "total": total,
        "fecha_pago": pago.fecha_pago,
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
    _: dict = Depends(get_current_user),
):
    filt: dict = {}
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

    # If q present, we need to filter by codcomprobante (cod/gestion) or estudiante name
    extra_or = []
    if q:
        ql = q.strip()
        if "/" in ql:
            try:
                cod_part, ges_part = ql.split("/", 1)
                extra_or.append(
                    {"codcomprobante": cod_part.zfill(5), "gestion": int(ges_part)}
                )
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
            async for t in db.tipos_pagos.find(
                {"nombre": {"$regex": ql, "$options": "i"}}, {"_id": 0, "id": 1}
            )
        ]
        if tp_ids:
            extra_or.append({"id_tipo_pago": {"$in": tp_ids}})

        filt["$or"] = extra_or

    cursor = db.pagos.aggregate(
        [
            {"$match": filt},
            {"$sort": {"created_at": -1}},
            {"$limit": 1000},
            *_PAGO_HYDRATE_PIPELINE,
        ]
    )
    return [Pago(**p) async for p in cursor]


@api.put("/pagos/{pago_id}", response_model=Pago)
async def update_pago(
    pago_id: str, body: PagoCreate, user: dict = Depends(require_roles("Administrador", "Caja"))
):
    pago = await db.pagos.find_one({"id": pago_id}, {"_id": 0})
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    if pago.get("anulado"):
        raise HTTPException(
            status_code=400, detail="No se puede editar un pago anulado"
        )

    update: dict = {}

    if body.id_estudiante and body.id_estudiante != pago["id_estudiante"]:
        if not await db.estudiantes.find_one({"id": body.id_estudiante}):
            raise HTTPException(status_code=400, detail="Estudiante no encontrado")
        update["id_estudiante"] = body.id_estudiante

    new_monto = pago["monto"]
    if body.id_tipo_pago and body.id_tipo_pago != pago["id_tipo_pago"]:
        tp = await db.tipos_pagos.find_one({"id": body.id_tipo_pago}, {"_id": 0})
        if not tp:
            raise HTTPException(status_code=400, detail="Tipo de pago no encontrado")
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

    await db.pagos.update_one({"id": pago_id}, {"$set": update})
    p = await db.pagos.find_one({"id": pago_id}, {"_id": 0})
    p = await _hydrate_pago(p)
    return Pago(**p)


@api.post("/pagos/{pago_id}/anular")
async def anular_pago(pago_id: str, usuario: dict = Depends(require_roles("Administrador"))):
    pago = await db.pagos.find_one({"id": pago_id})
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado.")
    if pago.get("anulado"):
        raise HTTPException(status_code=400, detail="El pago ya está anulado.")
    await db.pagos.update_one(
        {"id": pago_id},
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
    _: dict = Depends(require_roles("Administrador")),
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
    tipospagos_count = await db.tipos_pagos.count_documents({})
    pagos_hoy_count = await db.pagos.count_documents(
        {"fecha_pago": today, "anulado": False}
    )
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
    await db.usuarios.create_index("email", unique=True)
    # `id` indexes — used by $lookup foreignField joins in /api/pagos and /api/reportes
    await db.usuarios.create_index("id", unique=True)
    await db.estudiantes.create_index("id", unique=True)    
    await db.estudiantes.create_index("ci")
    await db.tipos_pagos.create_index("id", unique=True)    
    await db.pagos.create_index([("gestion", 1), ("codcomprobante", 1)])
    await db.pagos.create_index("fecha_pago")
    # filter indexes used by /api/pagos
    await db.pagos.create_index("created_by")
    await db.pagos.create_index("id_estudiante")
    await db.pagos.create_index("id_tipo_pago")

    admin = await db.usuarios.find_one({"email": ADMIN_EMAIL.lower()})
    if admin is None:
        await db.usuarios.insert_one(
            {
                "id": str(uuid.uuid4()),
                "email": ADMIN_EMAIL.lower(),
                "nombre": ADMIN_NAME,
                "rol": "Administrador",
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
