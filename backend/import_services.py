"""Server-side directory integration. Never exposes credentials to the browser."""
import json
import os
import unicodedata
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from client_models import ClienteCreate, UsuarioDirectorio


def _key(value):
    text = unicodedata.normalize("NFKD", str(value))
    return "".join(c.lower() for c in text if c.isalnum() and not unicodedata.combining(c))


def normalize_record(record, kind):
    if not isinstance(record, dict):
        raise ValueError("Cada resultado debe ser un objeto.")
    fields = {_key(k): v for k, v in record.items()}
    name = fields.get("nombre", fields.get("nombrecompleto"))
    if kind == "clientes":
        return ClienteCreate(
            ci=fields.get("ci") or "", cu=fields.get("cu") or "", nombre=name,
        ).model_dump()
    return UsuarioDirectorio(
        codigo=fields.get("codigo"), nombre=name, email=fields.get("email"),
    ).model_dump(mode="json")


async def directory_results(kind, q=""):
    prefix = {"clientes": "CLIENTS", "usuarios": "USERS"}[kind]
    url = os.getenv(f"{prefix}_IMPORT_API_URL", "").strip()
    if not url:
        raise HTTPException(503, f"El servicio de importación de {kind} no está configurado.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(503, "La URL del servicio de importación no es válida.")
    token = os.getenv(f"{prefix}_IMPORT_API_TOKEN")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 2_000_000:
                        raise HTTPException(502, "La respuesta del servicio excede el límite permitido.")
        rows = json.loads(data)
        if not isinstance(rows, list) or len(rows) > 10_000:
            raise ValueError("Se esperaba una lista de hasta 10000 registros.")
        result = [normalize_record(row, kind) for row in rows]
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, ValidationError):
        raise HTTPException(502, "No se pudo consultar el servicio o su lista tiene un formato inválido.")
    term = q.strip().casefold()
    if term:
        result = [row for row in result if any(term in str(v).casefold() for v in row.values())]
    # No IDs from the external service are retained. Creation uses each backend.
    return result
