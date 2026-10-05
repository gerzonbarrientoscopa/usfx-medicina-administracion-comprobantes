"""Shared client and directory contracts for MongoDB and SQL Server."""
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class ClienteCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ci: str = Field(default="", max_length=30)
    cu: str = Field(default="", max_length=50)
    nombre: str = Field(min_length=1, max_length=200)

    @field_validator("ci", "cu", "nombre", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_identifier(self):
        if not self.ci and not self.cu:
            raise ValueError("Indique al menos un C.I. o C.U.")
        return self


class Cliente(ClienteCreate):
    id: str


class UsuarioDirectorio(BaseModel):
    model_config = ConfigDict(extra="ignore")
    codigo: str = Field(pattern=r"^[0-9]{3}$")
    nombre: str = Field(min_length=1, max_length=200)
    email: EmailStr

    @field_validator("codigo", "nombre", "email", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value
