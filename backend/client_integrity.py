"""Mongo client reference guards, shared by every process using the database.

Pins and deletion gates deliberately never expire: a paused or uncertain write
must not outlive its protection. Unexpected write failures require reconciliation
before an abandoned pin/gate can be removed, not a timeout-based unlock.
"""
import uuid
from contextlib import asynccontextmanager

from fastapi import HTTPException


class ReferenceWrite:
    def __init__(self):
        self.started = False

    def begin_write(self):
        """Call immediately before dispatching a reference-changing DB write."""
        self.started = True


@asynccontextmanager
async def client_reference(db, ident):
    token = str(uuid.uuid4())
    acquired = await db.clientes.update_one(
        {"id": ident, "_client_deleting": {"$exists": False}},
        {"$addToSet": {"_client_writes": token}},
    )
    if not acquired.matched_count:
        raise HTTPException(400, "El cliente no existe o está siendo eliminado.")
    write = ReferenceWrite()
    completed = False
    try:
        yield write
        completed = True
    finally:
        # A failed/canceled insertion may still commit. Retain its pin even if
        # a read currently shows no reference. Other writers retain their pins.
        if completed or not write.started:
            await db.clientes.update_one(
                {"id": ident}, {"$pull": {"_client_writes": token}},
            )


async def delete_unreferenced_client(db, ident):
    token = str(uuid.uuid4())
    acquired = await db.clientes.update_one(
        {
            "id": ident,
            "_client_deleting": {"$exists": False},
            "_client_writes": {"$in": [None, []]},
        },
        {"$set": {"_client_deleting": token}},
    )
    if not acquired.matched_count:
        if not await db.clientes.find_one({"id": ident}):
            raise HTTPException(404, "Cliente no encontrado.")
        raise HTTPException(409, "El cliente tiene una operación en curso; vuelva a intentarlo.")
    deleting = False
    try:
        if (await db.pagos.find_one({"cliente_id": ident})
                or await db.alquileres.find_one({"cliente_id": ident})):
            raise HTTPException(400, "No se puede eliminar un cliente con pagos o alquileres registrados.")
        deleting = True
        await db.clientes.delete_one({"id": ident, "_client_deleting": token})
    finally:
        # Do not reopen the gate after a delete with an unknown outcome: it
        # could complete after a new writer has validated the client.
        if not deleting:
            await db.clientes.update_one(
                {"id": ident, "_client_deleting": token},
                {"$unset": {"_client_deleting": ""}},
            )
