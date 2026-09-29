"""SQL Server 2025 FastAPI service for Comprobantes USFX.

Requires ``pyodbc`` and Microsoft ODBC Driver 18 for SQL Server
(``pip install pyodbc``).  Set SQLSERVER_CONNECTION_STRING, or set
SQLSERVER_HOST, SQLSERVER_DATABASE, SQLSERVER_USER and SQLSERVER_PASSWORD.
For Windows authentication use SQLSERVER_TRUSTED_AUTH=1.  Connections are
created lazily; importing this module never contacts a database.
"""
from __future__ import annotations
import asyncio, json, os, re, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
import bcrypt, jwt, pyodbc
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr, ConfigDict

app=FastAPI(title="Comprobantes USFX (SQL Server)")
api=APIRouter(prefix="/api"); security=HTTPBearer()
JWT_SECRET_KEY=os.getenv("JWT_SECRET","change-this-secret"); JWT_ALGORITHM="HS256"
SUPER_ADMIN_EMAIL="admin@usfx.bo"; SUPER_ADMIN_ROLE="SuperAdmin"; ROLES=("Administrador","Caja","Consultas")

class AnyModel(BaseModel):
    model_config=ConfigDict(extra="allow")
class LoginRequest(AnyModel): email:EmailStr; password:str
class UserCreate(AnyModel): email:EmailStr; nombre:str; password:str=Field(min_length=4); rol:str; office_id:Optional[str]=None
class UserUpdate(AnyModel): nombre:Optional[str]=None; rol:Optional[str]=None; password:Optional[str]=None; office_id:Optional[str]=None
class OfficeCreate(AnyModel): nombre:str; prefijo_comprobante:str; suboficina:str=""; activa:bool=True
class EstudianteCreate(AnyModel): ci:str; cu:str=""; nombre:str; gestion:int; office_id:Optional[str]=None
class PersonaCreate(AnyModel): ci:str; nombre:str
class TipoPagoCreate(AnyModel): nombre:str; monto:Decimal; descripcion:str=""; inicio:str; fin:Optional[str]=None; office_id:Optional[str]=None
class AmbienteCreate(AnyModel): nombre:str; descripcion:str=""; horarios:list[dict]=[]; office_id:Optional[str]=None
class TarifaCreate(AnyModel): ambiente_id:str; nombre:str; modalidad:str; monto:Decimal; descripcion:str=""; desde:Optional[str]=None; hasta:Optional[str]=None
class AlquilerCreate(AnyModel): ambiente_id:str; tarifa_id:str; fecha:str; desde:Optional[str]=None; hasta:Optional[str]=None; cliente_tipo:str; cliente_id:str; cliente_documento:Optional[str]=None; cobrar_ahora:bool=False; office_id:Optional[str]=None
class PagoCreate(AnyModel): id_estudiante:str; fecha_pago:str; office_id:Optional[str]=None; id_tipo_pago:Optional[str]=None; cantidad:Optional[float]=None
class PagoItemCreate(AnyModel): id_tipo_pago:str; cantidad:float

def _connection_string():
    value=os.getenv("SQLSERVER_CONNECTION_STRING")
    if value:return value
    host=os.getenv("SQLSERVER_HOST","localhost"); db=os.getenv("SQLSERVER_DATABASE","ComprobantesDB")
    if os.getenv("SQLSERVER_TRUSTED_AUTH","").lower() in ("1","true","yes"):
        return f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={host};DATABASE={db};Trusted_Connection=yes;TrustServerCertificate=yes"
    return f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={host};DATABASE={db};UID={os.getenv('SQLSERVER_USER','')};PWD={os.getenv('SQLSERVER_PASSWORD','')};TrustServerCertificate=yes"
def _connect(): return pyodbc.connect(_connection_string(), autocommit=False)
def _rows(cur):
    cols=[x[0] for x in cur.description] if cur.description else []
    return [dict(zip(cols,row)) for row in cur.fetchall()]
def _json(v):
    if isinstance(v,(datetime,)): return v.astimezone(timezone.utc).isoformat()
    if isinstance(v,Decimal): return float(v)
    return v
def clean(row):
    return {k:_json(v) for k,v in row.items()} if row else None

async def sql(statement, params=(), *, one=False, write=False):
    def run():
        with _connect() as cn:
            cur=cn.cursor(); cur.execute(statement,tuple(params)); out=_rows(cur) if cur.description else []
            if one: out=out[0] if out else None
            elif cur.description: out=_rows(cur)
            else: out=[]
            if write: cn.commit()
            return clean(out) if one else [clean(x) for x in out]
    return await asyncio.to_thread(run)
async def tx(work):
    return await asyncio.to_thread(work)
def now(): return datetime.now(timezone.utc).isoformat()
def minutes(text):
    if not isinstance(text,str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",text): raise HTTPException(400,"La hora debe tener formato HH:MM.")
    return int(text[:2])*60+int(text[3:])
def validate_blocks(blocks):
    by={}
    for b in blocks:
        if b.get("dia") not in ("lunes","martes","miercoles","jueves","viernes","sabado","domingo"): raise HTTPException(422,"Día inválido.")
        start,end=minutes(b.get("desde")),minutes(b.get("hasta"))
        if start>=end: raise HTTPException(422,"La hora de fin debe ser posterior al inicio.")
        by.setdefault(b["dia"],[]).append((start,end))
    for values in by.values():
        values.sort()
        if any(b[0]<a[1] for a,b in zip(values,values[1:])): raise HTTPException(422,"Los horarios del mismo día no pueden superponerse.")
def covered(blocks,start,end):
    s,e=minutes(start),minutes(end); values=sorted((minutes(x["desde"]),minutes(x["hasta"])) for x in blocks)
    merged=[]
    for a,b in values:
        if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(merged[-1][1],b))
        else: merged.append((a,b))
    return any(a<=s and b>=e for a,b in merged)
WEEKDAYS=("lunes","martes","miercoles","jueves","viernes","sabado","domingo")
def day_blocks(rows, day):
    return [{"desde":x["desde"],"hasta":x["hasta"]} for x in rows if x["dia"]==day]
def hashpw(p): return bcrypt.hashpw(p.encode(),bcrypt.gensalt()).decode()
def token(u): return jwt.encode({"sub":u["id"],"email":u["email"],"rol":u["rol"],"exp":datetime.now(timezone.utc).timestamp()+28800},JWT_SECRET_KEY,algorithm=JWT_ALGORITHM)

async def current(credentials:HTTPAuthorizationCredentials=Depends(security)):
    try: payload=jwt.decode(credentials.credentials,JWT_SECRET_KEY,algorithms=[JWT_ALGORITHM]); uid=payload["sub"]
    except Exception: raise HTTPException(401,"Token inválido.")
    u=await sql("SELECT u.*,o.nombre office_nombre FROM usuarios u LEFT JOIN oficinas o ON o.id=u.office_id WHERE u.id=?",(uid,),one=True)
    if not u: raise HTTPException(401,"Usuario no encontrado.")
    u.pop("password_hash",None); return u
def roles(*allowed):
    async def dep(u=Depends(current)):
        if u["rol"] not in allowed and u["rol"]!=SUPER_ADMIN_ROLE: raise HTTPException(403,"Sin permisos para esta acción.")
        return u
    return dep
async def office(u, requested=None, active=False):
    oid=requested if u["rol"]==SUPER_ADMIN_ROLE else u.get("office_id")
    if u["rol"]!="SuperAdmin" and requested and requested!=oid: raise HTTPException(403,"Sin permisos para consultar otra oficina.")
    if not oid: raise HTTPException(400,"Seleccione una oficina.")
    q="SELECT * FROM oficinas WHERE id=?"+(" AND activa=1" if active else "")
    if not await sql(q,(oid,),one=True): raise HTTPException(404,"Oficina no encontrada o inactiva.")
    return oid
def page(items,total,pag,tam): return {"items":items,"total":total,"page":pag,"size":tam,"pages":max(1,(total+tam-1)//tam)}
async def hydrate_rental(r):
    if not r:return r
    a=await sql("SELECT nombre FROM ambientes WHERE id=?",(r["ambiente_id"],),one=True); t=await sql("SELECT nombre,modalidad FROM tarifas_ambientes WHERE id=?",(r["tarifa_id"],),one=True)
    r["ambiente_nombre"]=(a or {}).get("nombre"); r["tarifa_nombre"]=(t or {}).get("nombre"); r["modalidad"]=(t or {}).get("modalidad")
    r["tramos"]=await sql("SELECT CONVERT(varchar(5),desde,108) desde,CONVERT(varchar(5),hasta,108) hasta FROM alquiler_tramos WHERE alquiler_id=? ORDER BY desde",(r["id"],))
    o=await sql("SELECT nombre,suboficina,prefijo_comprobante FROM oficinas WHERE id=?",(r["office_id"],),one=True)
    if o:r["office_nombre"]=o["nombre"]; r["suboficina"]=o["suboficina"]; r["comprobante_display"]=f"{o['prefijo_comprobante']}-{r['cod_comprobante']} / {r['gestion']}" if r.get("cod_comprobante") else None
    return r
def allocate_receipt(c, office_id, year, origin, origin_id):
    """Must be called inside the caller's transaction; one ledger spans both sources."""
    c.execute("EXEC sp_getapplock @Resource=?,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=5000",(f"receipt:{office_id}:{year}",))
    c.execute("SELECT prefijo_comprobante FROM oficinas WITH(HOLDLOCK) WHERE id=?",(office_id,)); prefix=c.fetchone()[0]
    c.execute("SELECT siguiente FROM comprobante_contadores WITH(UPDLOCK,HOLDLOCK) WHERE office_id=? AND gestion=?",(office_id,year)); row=c.fetchone()
    if row is None: code=1; c.execute("INSERT INTO comprobante_contadores(office_id,gestion,siguiente) VALUES(?,?,?)",(office_id,year,2))
    else: code=row[0]; c.execute("UPDATE comprobante_contadores SET siguiente=siguiente+1 WHERE office_id=? AND gestion=?",(office_id,year))
    code=f"{code:05d}"; c.execute("INSERT INTO comprobante_asignaciones(office_id,gestion,codigo,origen,origen_id) VALUES(?,?,?,?,?)",(office_id,year,code,origin,origin_id))
    return code,prefix

@api.post("/auth/login")
async def login(b:LoginRequest,response:Response):
    u=await sql("SELECT * FROM usuarios WHERE email_key=LOWER(LTRIM(RTRIM(?)))",(str(b.email),),one=True)
    if not u or not bcrypt.checkpw(b.password.encode(),u["password_hash"].encode()): raise HTTPException(401,"Credenciales inválidas.")
    u.pop("password_hash",None); u["office_nombre"]=(await sql("SELECT nombre FROM oficinas WHERE id=?",(u["office_id"],),one=True) or {}).get("nombre")
    t=token(u); response.set_cookie("access_token",t,httponly=True,samesite="lax"); return {"token":t,"usuario":u}
@api.post("/auth/logout")
async def logout(response:Response): response.delete_cookie("access_token"); return {"ok":True}
@api.get("/auth/me")
async def me(u=Depends(current)): return u

@api.get("/oficinas")
async def offices(pag:int=1,tam:int=20,q:Optional[str]=None,u=Depends(current)):
    where="" if u["rol"]=="SuperAdmin" else " AND id=?"; args=[] if u["rol"]=="SuperAdmin" else [u["office_id"]]
    if q: where+=" AND nombre LIKE ?"; args.append("%"+q.strip()+"%")
    total=(await sql("SELECT COUNT(*) n FROM oficinas WHERE 1=1"+where,args,one=True))["n"]
    rows=await sql("SELECT * FROM oficinas WHERE 1=1"+where+" ORDER BY nombre OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",args+[(pag-1)*tam,tam])
    return page(rows,total,pag,tam)
@api.post("/oficinas",status_code=201)
async def create_office(b:OfficeCreate,u=Depends(roles(SUPER_ADMIN_ROLE))):
    oid=str(uuid.uuid4()); await sql("INSERT INTO oficinas(id,nombre,prefijo_comprobante,suboficina,activa) VALUES(?,?,?,?,?)",(oid,b.nombre.strip(),b.prefijo_comprobante.upper(),b.suboficina.strip(),b.activa),write=True)
    return await sql("SELECT * FROM oficinas WHERE id=?",(oid,),one=True)
@api.put("/oficinas/{oid}")
async def update_office(oid:str,b:OfficeCreate,u=Depends(roles(SUPER_ADMIN_ROLE))):
    await sql("UPDATE oficinas SET nombre=?,prefijo_comprobante=?,suboficina=?,activa=? WHERE id=?",(b.nombre,b.prefijo_comprobante.upper(),b.suboficina,b.activa,oid),write=True); return await sql("SELECT * FROM oficinas WHERE id=?",(oid,),one=True)
@api.delete("/oficinas/{oid}")
async def delete_office(oid:str,u=Depends(roles(SUPER_ADMIN_ROLE))):
    checks=("usuarios","estudiantes","tipos_pagos","ambientes","tarifas_ambientes","pagos","alquileres","comprobante_contadores")
    for table in checks:
        if await sql(f"SELECT TOP 1 id FROM {table} WHERE office_id=?",(oid,),one=True): raise HTTPException(400,"No se puede eliminar una oficina con registros asociados.")
    await sql("DELETE FROM oficinas WHERE id=?",(oid,),write=True); return {"ok":True}

@api.get("/usuarios")
async def users(pag:int=1,tam:int=10,office_id:Optional[str]=None,u=Depends(roles("Administrador"))):
    oid=await office(u,office_id); where="WHERE office_id=?"; args=[oid]
    total=(await sql("SELECT COUNT(*) n FROM usuarios "+where,args,one=True))["n"]
    rows=await sql("SELECT id,email,nombre,rol,office_id,created_at FROM usuarios "+where+" ORDER BY nombre OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",args+[(pag-1)*tam,tam])
    return page(rows,total,pag,tam)
@api.get("/usuarios/list")
async def users_list(office_id:Optional[str]=None,u=Depends(current)):
    oid=await office(u,office_id); return await sql("SELECT id,nombre,rol,office_id FROM usuarios WHERE office_id=? ORDER BY nombre",(oid,))
@api.post("/usuarios",status_code=201)
async def create_user(b:UserCreate,u=Depends(roles("Administrador"))):
    oid=await office(u,b.office_id,True)
    if b.rol not in ROLES: raise HTTPException(422,"Rol inválido.")
    if b.rol=="Administrador" and u["rol"]!=SUPER_ADMIN_ROLE: raise HTTPException(403,"Sólo el Super Admin asigna administradores.")
    ident=str(uuid.uuid4()); await sql("INSERT INTO usuarios(id,email,nombre,rol,office_id,password_hash) VALUES(?,?,?,?,?,?)",(ident,str(b.email).lower(),b.nombre,b.rol,oid,hashpw(b.password)),write=True)
    return await sql("SELECT id,email,nombre,rol,office_id,created_at FROM usuarios WHERE id=?",(ident,),one=True)
@api.put("/usuarios/{uid}")
async def update_user(uid:str,b:UserUpdate,u=Depends(roles("Administrador"))):
    oid=await office(u); sets=[]; args=[]
    target=await sql("SELECT * FROM usuarios WHERE id=? AND office_id=?",(uid,oid),one=True)
    if not target: raise HTTPException(404,"Usuario no encontrado.")
    if target["rol"]==SUPER_ADMIN_ROLE: raise HTTPException(403,"La cuenta del Super Admin está protegida.")
    if u["rol"]!=SUPER_ADMIN_ROLE and target["rol"]=="Administrador" and uid!=u["id"]: raise HTTPException(403,"No puede modificar administradores.")
    for col,val in (("nombre",b.nombre),("rol",b.rol),("office_id",b.office_id)):
        if val is not None: sets.append(col+"=?"); args.append(val)
    if b.password: sets.append("password_hash=?"); args.append(hashpw(b.password))
    if not sets: raise HTTPException(400,"Sin cambios.")
    args.extend([uid,oid]); await sql("UPDATE usuarios SET "+",".join(sets)+" WHERE id=? AND office_id=?",tuple(args),write=True)
    return await sql("SELECT id,email,nombre,rol,office_id,created_at FROM usuarios WHERE id=?",(uid,),one=True)
@api.delete("/usuarios/{uid}")
async def delete_user(uid:str,u=Depends(roles("Administrador"))):
    if uid==u["id"]: raise HTTPException(400,"No puedes eliminar tu propio usuario.")
    await sql("DELETE FROM usuarios WHERE id=? AND office_id=?",(uid,u.get("office_id")),write=True); return {"ok":True}

async def listing(table, fields, office_id, u, pag, tam, q=None):
    oid=await office(u,office_id); where="office_id=?"; args=[oid]
    if q:
        searchable={"estudiantes":"(nombre LIKE ? OR ci LIKE ? OR cu LIKE ?)","tipos_pagos":"nombre LIKE ?","ambientes":"nombre LIKE ?"}[table]
        where+=" AND "+searchable; args += ["%"+q+"%"]*(searchable.count("?"))
    total=(await sql(f"SELECT COUNT(*) n FROM {table} WHERE {where}",args,one=True))["n"]
    rows=await sql(f"SELECT {fields} FROM {table} WHERE {where} ORDER BY nombre OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",args+[(pag-1)*tam,tam])
    return page(rows,total,pag,tam)
@api.get("/estudiantes")
async def students(pag:int=1,tam:int=20,q:Optional[str]=None,office_id:Optional[str]=None,u=Depends(current)): return await listing("estudiantes","id,ci,cu,nombre,gestion,office_id",office_id,u,pag,tam,q)
@api.post("/estudiantes",status_code=201)
async def create_student(b:EstudianteCreate,u=Depends(roles("Administrador"))):
    oid=await office(u,b.office_id,True); ident=str(uuid.uuid4())
    if await sql("SELECT id FROM personas WHERE ci_key=LOWER(LTRIM(RTRIM(?)))",(b.ci,),one=True): raise HTTPException(400,"Este C.I. ya está registrado como Persona.")
    if b.cu and await sql("SELECT id FROM estudiantes WHERE office_id=? AND cu_key=LOWER(LTRIM(RTRIM(?)))",(oid,b.cu),one=True): raise HTTPException(400,"El C.U. ya existe en esta oficina.")
    await sql("INSERT INTO estudiantes(id,ci,cu,nombre,gestion,office_id) VALUES(?,?,?,?,?,?)",(ident,b.ci,b.cu,b.nombre,b.gestion,oid),write=True); return await sql("SELECT * FROM estudiantes WHERE id=?",(ident,),one=True)
@api.put("/estudiantes/{sid}")
async def update_student(sid:str,b:EstudianteCreate,u=Depends(roles("Administrador"))):
    await office(u,b.office_id)
    if await sql("SELECT id FROM personas WHERE ci_key=LOWER(LTRIM(RTRIM(?)))",(b.ci,),one=True): raise HTTPException(400,"Este C.I. ya está registrado como Persona.")
    if b.cu and await sql("SELECT id FROM estudiantes WHERE office_id=? AND cu_key=LOWER(LTRIM(RTRIM(?))) AND id<>?",(u["office_id"],b.cu,sid),one=True): raise HTTPException(400,"El C.U. ya existe en esta oficina.")
    await sql("UPDATE estudiantes SET ci=?,cu=?,nombre=?,gestion=? WHERE id=? AND office_id=?",(b.ci,b.cu,b.nombre,b.gestion,sid,u["office_id"]),write=True); return await sql("SELECT * FROM estudiantes WHERE id=?",(sid,),one=True)
@api.delete("/estudiantes/{sid}")
async def delete_student(sid:str,u=Depends(roles("Administrador"))): await sql("DELETE FROM estudiantes WHERE id=? AND office_id=?",(sid,u["office_id"]),write=True); return {"ok":True}
@api.get("/personas")
async def people(pag:int=1,tam:int=20,q:Optional[str]=None,u=Depends(current)):
    where=""; args=[]
    if q: where="WHERE nombre LIKE ? OR ci LIKE ?"; args=["%"+q+"%"]*2
    total=(await sql("SELECT COUNT(*) n FROM personas "+where,args,one=True))["n"]; rows=await sql("SELECT * FROM personas "+where+" ORDER BY nombre OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",args+[(pag-1)*tam,tam]); return page(rows,total,pag,tam)
@api.post("/personas",status_code=201)
async def create_person(b:PersonaCreate,u=Depends(roles("Administrador"))):
    if await sql("SELECT id FROM estudiantes WHERE ci_key=LOWER(LTRIM(RTRIM(?)))",(b.ci,),one=True): raise HTTPException(400,"Esta persona está registrada como estudiante.")
    ident=str(uuid.uuid4()); await sql("INSERT INTO personas(id,ci,nombre) VALUES(?,?,?)",(ident,b.ci.strip(),b.nombre.strip()),write=True); return await sql("SELECT * FROM personas WHERE id=?",(ident,),one=True)
@api.put("/personas/{pid}")
async def update_person(pid:str,b:PersonaCreate,u=Depends(roles("Administrador"))): await sql("UPDATE personas SET ci=?,nombre=? WHERE id=?",(b.ci,b.nombre,pid),write=True); return await sql("SELECT * FROM personas WHERE id=?",(pid,),one=True)
@api.delete("/personas/{pid}")
async def delete_person(pid:str,u=Depends(roles("Administrador"))): await sql("DELETE FROM personas WHERE id=?",(pid,),write=True); return {"ok":True}

@api.get("/tipos-pagos")
async def concepts(pag:int=1,tam:int=20,q:Optional[str]=None,office_id:Optional[str]=None,u=Depends(current)): return await listing("tipos_pagos","id,nombre,monto,descripcion,inicio,fin,office_id",office_id,u,pag,tam,q)
@api.post("/tipos-pagos",status_code=201)
async def create_concept(b:TipoPagoCreate,u=Depends(roles("Administrador"))):
    oid=await office(u,b.office_id,True); ident=str(uuid.uuid4()); await sql("INSERT INTO tipos_pagos(id,office_id,nombre,monto,descripcion,inicio,fin) VALUES(?,?,?,?,?,?,?)",(ident,oid,b.nombre,b.monto,b.descripcion,b.inicio,b.fin),write=True); return await sql("SELECT * FROM tipos_pagos WHERE id=?",(ident,),one=True)
@api.put("/tipos-pagos/{tid}")
async def update_concept(tid:str,b:TipoPagoCreate,u=Depends(roles("Administrador"))): await sql("UPDATE tipos_pagos SET nombre=?,monto=?,descripcion=?,inicio=?,fin=? WHERE id=? AND office_id=?",(b.nombre,b.monto,b.descripcion,b.inicio,b.fin,tid,u["office_id"]),write=True); return await sql("SELECT * FROM tipos_pagos WHERE id=?",(tid,),one=True)
@api.delete("/tipos-pagos/{tid}")
async def delete_concept(tid:str,u=Depends(roles("Administrador"))): await sql("DELETE FROM tipos_pagos WHERE id=? AND office_id=?",(tid,u["office_id"]),write=True); return {"ok":True}

@api.get("/ambientes")
async def environments(pag:int=1,tam:int=20,q:Optional[str]=None,office_id:Optional[str]=None,u=Depends(current)):
    result=await listing("ambientes","id,nombre,descripcion,office_id,created_at",office_id,u,pag,tam,q)
    for x in result["items"]:
        x["horarios"]=await sql("SELECT dia,CONVERT(varchar(5),desde,108) desde,CONVERT(varchar(5),hasta,108) hasta FROM ambiente_horarios WHERE ambiente_id=? ORDER BY dia,desde",(x["id"],))
    return result
@api.post("/ambientes",status_code=201)
async def create_environment(b:AmbienteCreate,u=Depends(roles("Administrador"))):
    validate_blocks(b.horarios); oid=await office(u,b.office_id,True); ident=str(uuid.uuid4())
    await sql("INSERT INTO ambientes(id,office_id,nombre,descripcion) VALUES(?,?,?,?)",(ident,oid,b.nombre,b.descripcion),write=True)
    for h in b.horarios:
        await sql("INSERT INTO ambiente_horarios(ambiente_id,dia,desde,hasta) VALUES(?,?,?,?)",(ident,["lunes","martes","miercoles","jueves","viernes","sabado","domingo"].index(h["dia"]),h["desde"],h["hasta"]),write=True)
    return (await environments(1,20,None,oid,u))["items"][0]
@api.put("/ambientes/{aid}")
async def update_environment(aid:str,b:AmbienteCreate,u=Depends(roles("Administrador"))):
    validate_blocks(b.horarios)
    # Existing future reservations are protected by the same room/date lock;
    # reject a schedule change that would strand a confirmed booking.
    future=await sql("SELECT DISTINCT fecha FROM alquileres WHERE ambiente_id=? AND fecha>=CONVERT(date,SYSUTCDATETIME()) AND estado IN(N'reservado',N'procesando',N'pagado')",(aid,))
    for row in future:
        existing=await sql("SELECT desde,hasta FROM alquiler_tramos t JOIN alquileres a ON a.id=t.alquiler_id WHERE a.ambiente_id=? AND a.fecha=? AND a.estado<>N'cancelado'",(aid,row["fecha"]))
        day=WEEKDAYS[row["fecha"].weekday() if hasattr(row["fecha"],"weekday") else 0]
        if any(not covered(day_blocks(b.horarios,day),str(x["desde"])[:5],str(x["hasta"])[:5]) for x in existing): raise HTTPException(400,"El nuevo horario no cubre una reserva futura.")
    await sql("UPDATE ambientes SET nombre=?,descripcion=? WHERE id=? AND office_id=?",(b.nombre,b.descripcion,aid,u["office_id"]),write=True)
    await sql("DELETE FROM ambiente_horarios WHERE ambiente_id=?",(aid,),write=True)
    for h in b.horarios: await sql("INSERT INTO ambiente_horarios(ambiente_id,dia,desde,hasta) VALUES(?,?,?,?)",(aid,["lunes","martes","miercoles","jueves","viernes","sabado","domingo"].index(h["dia"]),h["desde"],h["hasta"]),write=True)
    return await sql("SELECT * FROM ambientes WHERE id=?",(aid,),one=True)
@api.delete("/ambientes/{aid}")
async def delete_environment(aid:str,u=Depends(roles("Administrador"))): await sql("DELETE FROM ambientes WHERE id=? AND office_id=?",(aid,u["office_id"]),write=True); return {"ok":True}
@api.get("/tarifas-ambientes")
async def tariffs(ambiente_id:Optional[str]=None,office_id:Optional[str]=None,u=Depends(current)):
    oid=await office(u,office_id); q="SELECT * FROM tarifas_ambientes WHERE office_id=?"; args=[oid]
    if ambiente_id: q+=" AND ambiente_id=?"; args.append(ambiente_id)
    return await sql(q+" ORDER BY nombre",args)
@api.post("/tarifas-ambientes",status_code=201)
async def create_tariff(b:TarifaCreate,u=Depends(roles("Administrador"))):
    room=await sql("SELECT office_id FROM ambientes WHERE id=?",(b.ambiente_id,),one=True)
    if not room: raise HTTPException(404,"Ambiente no encontrado.")
    if room["office_id"]!=u.get("office_id") and u["rol"]!=SUPER_ADMIN_ROLE: raise HTTPException(403,"Sin permisos.")
    ident=str(uuid.uuid4()); await sql("INSERT INTO tarifas_ambientes(id,ambiente_id,office_id,nombre,modalidad,monto,descripcion,desde,hasta) VALUES(?,?,?,?,?,?,?,?,?)",(ident,b.ambiente_id,room["office_id"],b.nombre,b.modalidad,b.monto,b.descripcion,b.desde,b.hasta),write=True); return await sql("SELECT * FROM tarifas_ambientes WHERE id=?",(ident,),one=True)
@api.put("/tarifas-ambientes/{tid}")
async def update_tariff(tid:str,b:TarifaCreate,u=Depends(roles("Administrador"))): await sql("UPDATE tarifas_ambientes SET nombre=?,modalidad=?,monto=?,descripcion=?,desde=?,hasta=? WHERE id=? AND office_id=?",(b.nombre,b.modalidad,b.monto,b.descripcion,b.desde,b.hasta,tid,u["office_id"]),write=True); return await sql("SELECT * FROM tarifas_ambientes WHERE id=?",(tid,),one=True)
@api.delete("/tarifas-ambientes/{tid}")
async def delete_tariff(tid:str,u=Depends(roles("Administrador"))): await sql("DELETE FROM tarifas_ambientes WHERE id=? AND office_id=?",(tid,u["office_id"]),write=True); return {"ok":True}

@api.get("/alquileres/clientes")
async def rental_clients(q:str="",u=Depends(current)):
    oid=await office(u); like="%"+q+"%"
    return await sql("SELECT TOP 50 N'persona' tipo,id,nombre,ci FROM personas WHERE nombre LIKE ? OR ci LIKE ? UNION ALL SELECT N'estudiante',id,nombre,ci FROM estudiantes WHERE office_id=? AND (nombre LIKE ? OR ci LIKE ? OR cu LIKE ?)",(like,like,oid,like,like,like))
@api.get("/alquileres")
async def rentals(ambiente_id:str,fecha_desde:str,fecha_hasta:str,office_id:Optional[str]=None,u=Depends(roles("Administrador","Caja","Consultas"))):
    try: start=datetime.strptime(fecha_desde,"%Y-%m-%d").date(); end=datetime.strptime(fecha_hasta,"%Y-%m-%d").date()
    except ValueError: raise HTTPException(400,"La fecha debe tener formato YYYY-MM-DD.")
    if end<start or (end-start).days>366: raise HTTPException(400,"Rango de fechas inválido.")
    oid=await office(u,office_id); room=await sql("SELECT office_id FROM ambientes WHERE id=?",(ambiente_id,),one=True)
    if not room or room["office_id"]!=oid: raise HTTPException(404,"Ambiente no encontrado en esa oficina.")
    rows=await sql("SELECT * FROM alquileres WHERE ambiente_id=? AND fecha>=? AND fecha<=? AND estado<>N'confirmando' ORDER BY fecha,created_at",(ambiente_id,fecha_desde,fecha_hasta))
    return [await hydrate_rental(x) for x in rows]
@api.get("/alquileres/{rid}")
async def rental(rid:str,u=Depends(current)):
    r=await sql("SELECT * FROM alquileres WHERE id=? AND office_id=?",(rid,await office(u)),one=True)
    if not r or r["estado"]=="confirmando": raise HTTPException(404,"Alquiler no encontrado.")
    return await hydrate_rental(r)
@api.post("/alquileres",status_code=201)
async def create_rental(b:AlquilerCreate,u=Depends(roles("Administrador","Caja"))):
    oid=await office(u,b.office_id,True); room=await sql("SELECT office_id FROM ambientes WHERE id=?",(b.ambiente_id,),one=True)
    tariff=await sql("SELECT * FROM tarifas_ambientes WHERE id=? AND ambiente_id=?",(b.tarifa_id,b.ambiente_id),one=True)
    if not room or not tariff or room["office_id"]!=oid: raise HTTPException(404,"Ambiente o tarifa no encontrados.")
    if b.cliente_tipo=="persona": payer=await sql("SELECT id,nombre,ci,NULL cu FROM personas WHERE id=?",(b.cliente_id,),one=True)
    else: payer=await sql("SELECT id,nombre,ci,cu,office_id FROM estudiantes WHERE id=?",(b.cliente_id,),one=True)
    if not payer: raise HTTPException(400,"El cliente seleccionado no existe.")
    if b.cliente_tipo=="estudiante" and payer.get("office_id")!=oid and u["rol"]!=SUPER_ADMIN_ROLE and (b.cliente_documento or "").strip().casefold() not in {payer["ci"].strip().casefold(),(payer.get("cu") or "").strip().casefold()}: raise HTTPException(400,"Para un estudiante de otra oficina, confirme su C.I. o C.U.")
    try: rental_date=datetime.strptime(b.fecha,"%Y-%m-%d").date()
    except ValueError: raise HTTPException(400,"La fecha debe tener formato YYYY-MM-DD.")
    schedules=await sql("SELECT dia,CONVERT(varchar(5),desde,108) desde,CONVERT(varchar(5),hasta,108) hasta FROM ambiente_horarios WHERE ambiente_id=?",(b.ambiente_id,))
    blocks=day_blocks(schedules,WEEKDAYS[rental_date.weekday()])
    if b.desde: minutes(b.desde)
    if b.hasta: minutes(b.hasta)
    if b.desde and b.hasta and minutes(b.desde)>=minutes(b.hasta): raise HTTPException(400,"La hora de fin debe ser posterior al inicio.")
    quantity=Decimal(1)
    if tariff["modalidad"] in ("hora","actividad"):
        if not b.desde or not b.hasta: raise HTTPException(400,"Indique las horas de inicio y fin.")
        quantity=(Decimal(minutes(b.hasta)-minutes(b.desde))/Decimal(60)) if tariff["modalidad"]=="hora" else Decimal(1)
        if not covered(blocks,b.desde,b.hasta): raise HTTPException(400,"El horario solicitado no está cubierto por un bloque disponible.")
    elif tariff["modalidad"] in ("manana","tarde") and (b.desde is not None and b.desde!=str(tariff["desde"])[:5] or b.hasta is not None and b.hasta!=str(tariff["hasta"])[:5]): raise HTTPException(400,"El horario debe coincidir con la tarifa.")
    elif tariff["modalidad"] in ("manana","tarde"):
        if not covered(blocks,str(tariff["desde"])[:5],str(tariff["hasta"])[:5]): raise HTTPException(400,"La tarifa no está cubierta por el horario disponible.")
        b.desde=str(tariff["desde"])[:5]; b.hasta=str(tariff["hasta"])[:5]
    elif tariff["modalidad"]=="dia" and (b.desde or b.hasta): raise HTTPException(400,"La modalidad día no admite horas.")
    elif tariff["modalidad"]=="dia":
        if not blocks: raise HTTPException(400,"El ambiente no tiene horario disponible ese día.")
    tramos=([{"desde":b.desde,"hasta":b.hasta}] if tariff["modalidad"]!="dia" else blocks)
    total=(Decimal(str(tariff["monto"]))*quantity).quantize(Decimal("0.01"))
    ident=str(uuid.uuid4()); estado="confirmando"; gestion=int(b.fecha[:4])
    # The room/date application lock and serializable transaction are mandatory: see Tablas.Sql.
    def reserve():
        with _connect() as cn:
            c=cn.cursor(); c.execute("EXEC sp_getapplock @Resource=?,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=5000",(f"room:{b.ambiente_id}:{b.fecha}",))
            c.execute("INSERT INTO alquileres(id,office_id,ambiente_id,tarifa_id,fecha,cliente_tipo,cliente_id,cliente_documento,cliente_nombre,cliente_ci,cliente_cu,estado,total,cantidad,monto,gestion,confirmation_started_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(ident,oid,b.ambiente_id,b.tarifa_id,b.fecha,b.cliente_tipo,b.cliente_id,b.cliente_documento,payer["nombre"],payer["ci"],payer.get("cu"),estado,total,quantity,tariff["monto"],gestion,datetime.now(timezone.utc)))
            c.execute("INSERT INTO ambiente_ocupacion(ambiente_id,fecha) SELECT ?,? WHERE NOT EXISTS(SELECT 1 FROM ambiente_ocupacion WHERE ambiente_id=? AND fecha=?)",(b.ambiente_id,b.fecha,b.ambiente_id,b.fecha))
            for tramo in tramos:
                start,end=tramo["desde"],tramo["hasta"]
                c.execute("SELECT id FROM ocupacion_intervalos WITH (UPDLOCK,HOLDLOCK) WHERE ambiente_id=? AND fecha=? AND desde<? AND hasta>?",(b.ambiente_id,b.fecha,end,start))
                if c.fetchone(): raise HTTPException(409,"El horario solicitado ya está reservado.")
                c.execute("INSERT INTO ocupacion_intervalos(ambiente_id,fecha,alquiler_id,desde,hasta) VALUES(?,?,?,?,?)",(b.ambiente_id,b.fecha,ident,start,end))
                c.execute("INSERT INTO alquiler_tramos(alquiler_id,desde,hasta) VALUES(?,?,?)",(ident,start,end))
            c.execute("UPDATE alquileres SET estado=N'reservado',confirmation_started_at=NULL WHERE id=? AND estado=N'confirmando'",(ident,))
            cn.commit()
    await tx(reserve)
    result=await hydrate_rental(await sql("SELECT * FROM alquileres WHERE id=?",(ident,),one=True))
    if b.cobrar_ahora: return await pay_rental(ident,u)
    return result
@api.post("/alquileres/{rid}/pagar")
async def pay_rental(rid:str,u=Depends(roles("Administrador","Caja"))):
    oid=await office(u)
    def pay():
        with _connect() as cn:
            c=cn.cursor(); c.execute("SELECT * FROM alquileres WITH(UPDLOCK,HOLDLOCK) WHERE id=? AND office_id=?",(rid,oid)); r=c.fetchone()
            if not r: raise HTTPException(404,"Alquiler no encontrado.")
            # Idempotent transition: a repeated request returns the paid row
            # and never allocates a second shared receipt.
            c.execute("SELECT estado FROM alquileres WHERE id=? AND office_id=?",(rid,oid)); state=c.fetchone()[0]
            if state=="pagado": return
            if state!="reservado": raise HTTPException(400,"Solo se puede pagar un alquiler reservado.")
            year=datetime.now(timezone.utc).year; code,prefix=allocate_receipt(c,oid,year,"alquiler",rid)
            c.execute("UPDATE alquileres SET estado=N'pagado',gestion=?,cod_comprobante=?,prefijo_comprobante=?,comprobante_display=?,paid_by=?,fecha_pago=SYSUTCDATETIME() WHERE id=?",(year,code,prefix,f"{prefix}-{code} / {year}",u["id"],rid)); cn.commit()
    await tx(pay); return await hydrate_rental(await sql("SELECT * FROM alquileres WHERE id=?",(rid,),one=True))
@api.post("/alquileres/{rid}/cancelar")
async def cancel_rental(rid:str,u=Depends(roles("Administrador","Caja"))):
    oid=await office(u)
    def cancel():
        with _connect() as cn:
            c=cn.cursor(); c.execute("UPDATE alquileres SET estado=N'cancelado' WHERE id=? AND office_id=? AND estado=N'reservado'",(rid,oid)); changed=c.rowcount
            if changed: c.execute("DELETE FROM ocupacion_intervalos WHERE alquiler_id=?",(rid,))
            cn.commit(); return changed
    changed=await tx(cancel)
    if not changed:
        latest=await sql("SELECT * FROM alquileres WHERE id=? AND office_id=?",(rid,oid),one=True)
        if not latest: raise HTTPException(404,"Alquiler no encontrado.")
        if latest["estado"]!="cancelado": raise HTTPException(400,"Solo se puede cancelar un alquiler reservado.")
    return await hydrate_rental(await sql("SELECT * FROM alquileres WHERE id=?",(rid,),one=True))
@api.get("/pagos/preview-comprobante")
async def preview(office_id:Optional[str]=None,u=Depends(roles("Administrador","Caja"))):
    oid=await office(u,office_id,True); year=datetime.now(timezone.utc).year
    row=await sql("SELECT siguiente FROM comprobante_contadores WHERE office_id=? AND gestion=?",(oid,year),one=True)
    code=f"{(row['siguiente'] if row else 1):05d}"; o=await sql("SELECT prefijo_comprobante FROM oficinas WHERE id=?",(oid,),one=True)
    return {"cod_comprobante":code,"gestion":year,"prefijo_comprobante":o["prefijo_comprobante"],"office_id":oid,"display":f"{o['prefijo_comprobante']}-{code} / {year}"}
@api.post("/pagos",status_code=201)
async def create_payment(b:PagoCreate,u=Depends(roles("Administrador","Caja"))):
    oid=await office(u,b.office_id,True); ident=str(uuid.uuid4()); year=datetime.now(timezone.utc).year
    def create():
        with _connect() as cn:
            c=cn.cursor()
            c.execute("SELECT id FROM estudiantes WHERE id=? AND office_id=?",(b.id_estudiante,oid))
            if not c.fetchone(): raise HTTPException(400,"Estudiante no encontrado en esta oficina.")
            code,prefix=allocate_receipt(c,oid,year,"pago",ident)
            state="emitido" if b.id_tipo_pago else "borrador"
            c.execute("INSERT INTO pagos(id,office_id,id_estudiante,fecha_pago,gestion,cod_comprobante,prefijo_comprobante,estado,created_by) VALUES(?,?,?,?,?,?,?,?,?)",(ident,oid,b.id_estudiante,b.fecha_pago,year,code,prefix,state,u["id"]))
            if b.id_tipo_pago:
                c.execute("SELECT nombre,monto FROM tipos_pagos WHERE id=? AND office_id=?",(b.id_tipo_pago,oid)); t=c.fetchone()
                if not t: raise HTTPException(400,"Tipo de pago no encontrado en esta oficina.")
                qty=b.cantidad or 1; c.execute("INSERT INTO pago_items(id,pago_id,id_tipo_pago,cantidad,monto) VALUES(?,?,?,?,?)",(str(uuid.uuid4()),ident,b.id_tipo_pago,qty,t[1]))
                c.execute("UPDATE pagos SET monto=?,total=? WHERE id=?",(t[1],t[1]*qty,ident))
            cn.commit()
    await tx(create)
    return await sql("SELECT * FROM pagos WHERE id=?",(ident,),one=True)
@api.post("/pagos/{pid}/items")
async def add_item(pid:str,b:PagoItemCreate,u=Depends(roles("Administrador","Caja"))):
    await sql("INSERT INTO pago_items(id,pago_id,id_tipo_pago,cantidad,monto) SELECT ?,?,?,?,monto FROM tipos_pagos WHERE id=?",(str(uuid.uuid4()),pid,b.id_tipo_pago,b.cantidad,b.id_tipo_pago),write=True)
    await sql("UPDATE pagos SET total=(SELECT COALESCE(SUM(cantidad*monto),0) FROM pago_items WHERE pago_id=?),monto=(SELECT COALESCE(SUM(cantidad*monto),0) FROM pago_items WHERE pago_id=?) WHERE id=?",(pid,pid,pid),write=True); return await sql("SELECT * FROM pagos WHERE id=?",(pid,),one=True)
@api.post("/pagos/{pid}/finalizar")
async def finalize_payment(pid:str,u=Depends(roles("Administrador","Caja"))):
    await sql("UPDATE pagos SET estado=N'emitido' WHERE id=? AND office_id=?",(pid,u.get("office_id")),write=True); return await sql("SELECT * FROM pagos WHERE id=?",(pid,),one=True)
@api.delete("/pagos/{pid}/borrador")
async def delete_draft(pid:str,u=Depends(roles("Administrador","Caja"))):
    oid=u.get("office_id")
    def discard():
        with _connect() as cn:
            c=cn.cursor(); c.execute("SELECT office_id,gestion,cod_comprobante FROM pagos WITH(UPDLOCK,HOLDLOCK) WHERE id=? AND office_id=? AND estado=N'borrador'",(pid,oid)); p=c.fetchone()
            if not p: raise HTTPException(404,"Comprobante no encontrado.")
            reused=False
            c.execute("EXEC sp_getapplock @Resource=?,@LockMode='Exclusive',@LockOwner='Transaction'",(f"receipt:{p[0]}:{p[1]}",))
            c.execute("SELECT siguiente FROM comprobante_contadores WITH(UPDLOCK,HOLDLOCK) WHERE office_id=? AND gestion=?",(p[0],p[1])); n=c.fetchone()
            if n and p[2] and int(p[2])==n[0]-1:
                c.execute("UPDATE comprobante_contadores SET siguiente=siguiente-1 WHERE office_id=? AND gestion=? AND siguiente=?",(p[0],p[1],n[0])); reused=c.rowcount==1
            c.execute("DELETE FROM comprobante_asignaciones WHERE office_id=? AND gestion=? AND codigo=?",(p[0],p[1],p[2])); c.execute("DELETE FROM pagos WHERE id=?",(pid,)); cn.commit(); return reused
    return {"ok":True,"correlativo_reutilizado":await tx(discard)}
@api.get("/pagos/{pid}")
async def get_payment(pid:str,u=Depends(current)): return await sql("SELECT * FROM pagos WHERE id=? AND office_id=?",(pid,await office(u)),one=True)
@api.get("/pagos")
async def payments(pag:int=1,tam:int=20,q:Optional[str]=None,id_tipo_pago:Optional[str]=None,fecha_desde:Optional[str]=None,fecha_hasta:Optional[str]=None,incluir_anulados:bool=True,created_by:Optional[str]=None,office_id:Optional[str]=None,u=Depends(current)):
    oid=await office(u,office_id); clauses=["office_id=?","estado<>N'borrador'"]; args=[oid]
    if not incluir_anulados: clauses.append("anulado=0")
    if created_by: clauses.append("created_by=?"); args.append(created_by)
    if fecha_desde: clauses.append("fecha_pago>=?"); args.append(fecha_desde)
    if fecha_hasta: clauses.append("fecha_pago<=?"); args.append(fecha_hasta)
    if id_tipo_pago: clauses.append("EXISTS(SELECT 1 FROM pago_items pi WHERE pi.pago_id=pagos.id AND pi.id_tipo_pago=?)"); args.append(id_tipo_pago)
    if q: clauses.append("(cod_comprobante LIKE ? OR id_estudiante IN(SELECT id FROM estudiantes WHERE nombre LIKE ? OR ci LIKE ? OR cu LIKE ?))"); args += ["%"+q+"%"]*4
    where=" AND ".join(clauses); total=(await sql("SELECT COUNT(*) n FROM pagos WHERE "+where,args,one=True))["n"]; rows=await sql("SELECT * FROM pagos WHERE "+where+" ORDER BY created_at DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",args+[(pag-1)*tam,tam]); return page(rows,total,pag,tam)
@api.put("/pagos/{pid}")
async def update_payment(pid:str,b:PagoCreate,u=Depends(roles("Administrador","Caja"))): await sql("UPDATE pagos SET fecha_pago=? WHERE id=? AND office_id=?",(b.fecha_pago,pid,u.get("office_id")),write=True); return await sql("SELECT * FROM pagos WHERE id=?",(pid,),one=True)
@api.post("/pagos/{pid}/anular")
async def void_payment(pid:str,u=Depends(roles("Administrador","Caja"))): await sql("UPDATE pagos SET anulado=1,anulado_at=SYSUTCDATETIME(),anulado_by=? WHERE id=? AND office_id=?",(u["id"],pid,u.get("office_id")),write=True); return await sql("SELECT * FROM pagos WHERE id=?",(pid,),one=True)
@api.get("/comprobantes")
async def receipts(pag:int=1,tam:int=20,q:Optional[str]=None,u=Depends(current)):
    oid=await office(u); like="%"+(q or "")+"%"
    rows=await sql("SELECT TOP 100 p.id,p.cod_comprobante,p.total,p.fecha_pago,N'estudiantil' origen FROM pagos p WHERE p.office_id=? AND (p.cod_comprobante LIKE ? OR p.id LIKE ?) UNION ALL SELECT a.id,a.cod_comprobante,a.total,a.fecha_pago,N'alquiler' FROM alquileres a WHERE a.office_id=? AND (a.cod_comprobante LIKE ? OR a.id LIKE ?) ORDER BY fecha_pago DESC",(oid,like,like,oid,like,like))
    return page(rows[pag and (pag-1)*tam:pag*tam],len(rows),pag,tam)
@api.get("/reportes")
async def reports(u=Depends(current),desde:Optional[str]=None,hasta:Optional[str]=None):
    oid=await office(u); pagos=await sql("SELECT * FROM pagos WHERE office_id=? AND estado<>N'borrador' AND (? IS NULL OR fecha_pago>=?) AND (? IS NULL OR fecha_pago<=?)",(oid,desde,desde,hasta,hasta)); rentals=await sql("SELECT * FROM alquileres WHERE office_id=? AND estado=N'pagado' AND (? IS NULL OR fecha_pago>=?) AND (? IS NULL OR fecha_pago<?)",(oid,desde,desde,hasta,hasta))
    anulados=sum(float(x.get("total") or 0) for x in pagos if x.get("anulado")); student=sum(float(x.get("total") or 0) for x in pagos if not x.get("anulado")); rent=sum(float(x.get("total") or 0) for x in rentals)
    return {"desde":desde,"hasta":hasta,"office_id":oid,"pagos":pagos,"alquileres":rentals,"totales":{"validos":student+rent,"estudiantiles":student,"alquileres":rent,"anulados":anulados,"diferencia":student+rent-anulados,"count_validos":sum(not x.get("anulado") for x in pagos)+len(rentals),"count_anulados":sum(bool(x.get("anulado")) for x in pagos)}}
@api.get("/dashboard/stats")
async def dashboard(office_id:Optional[str]=None,u=Depends(current)):
    oid=await office(u,office_id); day=datetime.now(timezone.utc).date().isoformat()
    p=await sql("SELECT COUNT(*) n,COALESCE(SUM(total),0) total FROM pagos WHERE office_id=? AND fecha_pago=? AND anulado=0 AND estado<>N'borrador'",(oid,day),one=True)
    r=await sql("SELECT COUNT(*) n,COALESCE(SUM(total),0) total FROM alquileres WHERE office_id=? AND fecha=? AND estado=N'pagado'",(oid,day),one=True)
    return {"pagos_hoy":p["n"],"ingresos_hoy":float(p["total"])+float(r["total"]),"estudiantes":(await sql("SELECT COUNT(*) n FROM estudiantes WHERE office_id=?",(oid,),one=True))["n"],"tipos_pagos":(await sql("SELECT COUNT(*) n FROM tipos_pagos WHERE office_id=?",(oid,),one=True))["n"],"alquileres_hoy":r["n"]}
@api.get("/")
async def root(): return {"message":"Comprobantes USFX SQL Server"}
app.include_router(api)

async def reconcile_startup():
    """Validate the separately-run Tablas.Sql schema, repair expired work, and seed
    the configured administrator.  It intentionally never performs DDL."""
    required=("oficinas","usuarios","estudiantes","ambientes","ambiente_horarios","tarifas_ambientes","pagos","pago_items","alquileres","alquiler_tramos","ambiente_ocupacion","ocupacion_intervalos","comprobante_contadores","comprobante_asignaciones")
    for table in required:
        if not await sql("SELECT OBJECT_ID(?,N'U') id",(f"dbo.{table}",),one=True): raise RuntimeError(f"Falta la tabla dbo.{table}; ejecute backend/Tablas.Sql.")
    await sql("UPDATE alquileres SET estado=N'reservado',payment_token=NULL,processing_lease_until=NULL,processing_started_at=NULL WHERE estado=N'procesando' AND processing_lease_until<=SYSUTCDATETIME()",write=True)
    await sql("UPDATE alquileres SET estado=N'cancelado',confirmation_started_at=NULL WHERE estado=N'confirmando' AND confirmation_started_at<DATEADD(minute,-30,SYSUTCDATETIME())",write=True)
    await sql("DELETE i FROM ocupacion_intervalos i LEFT JOIN alquileres a ON a.id=i.alquiler_id WHERE a.id IS NULL OR a.estado=N'cancelado'",write=True)
    email=os.getenv("SUPER_ADMIN_EMAIL",SUPER_ADMIN_EMAIL).lower(); password=os.getenv("ADMIN_PASSWORD"); name=os.getenv("ADMIN_NAME","Administrador")
    if password and not await sql("SELECT id FROM usuarios WHERE email_key=?",(email,),one=True):
        await sql("INSERT INTO usuarios(id,email,nombre,rol,password_hash) VALUES(?,?,?,?,?)",(str(uuid.uuid4()),email,name,SUPER_ADMIN_ROLE,hashpw(password)),write=True)
@app.on_event("startup")
async def startup():
    await reconcile_startup()