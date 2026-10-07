"""Unified client routes with interchangeable storage implementations."""
import uuid
from fastapi import Depends, HTTPException, Query
from client_models import Cliente, ClienteCreate
from import_services import directory_results
from client_integrity import delete_unreferenced_client


class MongoClientes:
    def __init__(self, get_db):
        self.get_db = get_db

    @property
    def db(self):
        return self.get_db()

    async def list(self, term, page, size):
        import re
        query = {"$or": [
            {key: {"$regex": re.escape(term), "$options": "i"}}
            for key in ("ci", "cu", "nombre")
        ]} if term else {}
        count = await self.db.clientes.count_documents(query)
        rows = await self.db.clientes.find(
            query, {"_id": 0, "id": 1, "ci": 1, "cu": 1, "nombre": 1}
        ).sort([("nombre", 1), ("id", 1)]).skip((page - 1) * size).limit(size).to_list(size)
        return rows, count

    async def save(self, body, ident=None):
        from pymongo.errors import DuplicateKeyError
        values = body.model_dump()
        values.update(ci_key=body.ci.lower(), cu_key=body.cu.lower())
        if ident and not await self.db.clientes.find_one({"id": ident}):
            raise HTTPException(404, "Cliente no encontrado.")
        try:
            if ident:
                await self.db.clientes.update_one({"id": ident}, {"$set": values})
            else:
                ident = str(uuid.uuid4())
                await self.db.clientes.insert_one({"id": ident, **values})
        except DuplicateKeyError:
            raise HTTPException(400, "Ya existe un cliente con este C.I. o C.U.")
        return {"id": ident, **body.model_dump()}

    async def delete(self, ident):
        await delete_unreferenced_client(self.db, ident)


class SQLClientes:
    def __init__(self, sql):
        self.sql = sql

    async def list(self, term, page, size):
        # Escape SQL LIKE wildcard characters, matching Mongo's literal search.
        term = term.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
        where = " WHERE nombre LIKE ? OR ci LIKE ? OR cu LIKE ?" if term else ""
        args = ["%" + term + "%"] * 3 if term else []
        count = (await self.sql("SELECT COUNT(*) n FROM clientes" + where, args, one=True))["n"]
        rows = await self.sql(
            "SELECT id,ci,cu,nombre FROM clientes" + where
            + " ORDER BY nombre,id OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
            args + [(page - 1) * size, size],
        )
        return rows, count

    async def save(self, body, ident=None):
        if ident and not await self.sql("SELECT id FROM clientes WHERE id=?", (ident,), one=True):
            raise HTTPException(404, "Cliente no encontrado.")
        duplicate = await self.sql(
            "SELECT id FROM clientes WHERE id<>? AND "
            "((?<>N'' AND ci_key=LOWER(?)) OR (?<>N'' AND cu_key=LOWER(?)))",
            (ident or 0, body.ci, body.ci, body.cu, body.cu), one=True,
        )
        if duplicate:
            raise HTTPException(400, "Ya existe un cliente con este C.I. o C.U.")
        if ident:
            await self.sql("UPDATE clientes SET ci=?,cu=?,nombre=? WHERE id=?",
                           (body.ci, body.cu, body.nombre, ident), write=True)
        else:
            ident = (await self.sql(
                "INSERT INTO clientes(ci,cu,nombre) OUTPUT INSERTED.id VALUES(?,?,?)",
                (body.ci, body.cu, body.nombre), one=True, write=True,
            ))["id"]
        return {"id": str(ident), **body.model_dump()}

    async def delete(self, ident):
        if not await self.sql("SELECT id FROM clientes WHERE id=?", (ident,), one=True):
            raise HTTPException(404, "Cliente no encontrado.")
        if await self.sql(
            "SELECT TOP 1 id FROM pagos WHERE cliente_id=? UNION ALL "
            "SELECT TOP 1 id FROM alquileres WHERE cliente_id=?", (ident, ident), one=True,
        ):
            raise HTTPException(400, "No se puede eliminar un cliente con pagos o alquileres registrados.")
        await self.sql("DELETE FROM clientes WHERE id=?", (ident,), write=True)


def register_client_routes(api, repository, read_access, write_access, admin_access):
    @api.get("/clientes")
    async def clients(
        pag: int = Query(1, ge=1), tam: int = Query(20, ge=1, le=100),
        textoBuscar: str = "", user=Depends(read_access),
    ):
        rows, count = await repository.list(textoBuscar.strip(), pag, tam)
        return {"items": [Cliente(**row) for row in rows], "total": count, "page": pag,
                "size": tam, "pages": max(1, (count + tam - 1) // tam)}

    @api.get("/clientes/buscar")
    async def search_clients(q: str = "", user=Depends(read_access)):
        if len(q.strip()) < 2:
            return []
        rows, _ = await repository.list(q.strip(), 1, 20)
        return [Cliente(**row) for row in rows]

    @api.get("/clientes/importacion")
    async def import_clients(q: str = "", user=Depends(write_access)):
        return await directory_results("clientes", q)

    @api.get("/usuarios/importacion")
    async def import_users(q: str = "", user=Depends(admin_access)):
        return await directory_results("usuarios", q)

    @api.post("/clientes", response_model=Cliente, status_code=201)
    async def create_client(body: ClienteCreate, user=Depends(write_access)):
        return await repository.save(body)

    @api.put("/clientes/{ident}", response_model=Cliente)
    async def update_client(ident: str, body: ClienteCreate, user=Depends(write_access)):
        return await repository.save(body, ident)

    @api.delete("/clientes/{ident}")
    async def delete_client(ident: str, user=Depends(write_access)):
        await repository.delete(ident)
        return {"ok": True}
