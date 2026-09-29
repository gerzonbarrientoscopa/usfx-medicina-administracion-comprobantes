/* Comprobantes USFX - SQL Server 2025 schema
   Run with sqlcmd (GO separators are intentional).  This script is additive and
   may be run repeatedly; it never drops data.  Receipt numbers are allocated
   through comprobante_asignaciones (the service locks that row); the unique
   filtered indexes on both source tables are a second line of defence.
   Interval claims and lease expiry cannot be expressed safely by a normal
   unique constraint.  serverSQL performs them in one transaction, taking
   UPDLOCK/HOLDLOCK on the room/date row and sp_getapplock on its resource.
*/
IF DB_ID(N'ComprobantesDB') IS NULL
BEGIN
    CREATE DATABASE ComprobantesDB;
END
GO
USE ComprobantesDB;
GO
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.oficinas','U') IS NULL
CREATE TABLE dbo.oficinas (
 id nvarchar(64) NOT NULL CONSTRAINT PK_oficinas PRIMARY KEY,
 nombre nvarchar(200) NOT NULL, nombre_key AS LOWER(LTRIM(RTRIM(nombre))) PERSISTED,
 prefijo_comprobante char(3) NOT NULL, suboficina nvarchar(100) NOT NULL CONSTRAINT DF_oficinas_sub DEFAULT N'',
 activa bit NOT NULL CONSTRAINT DF_oficinas_activa DEFAULT 1, created_at datetime2(3) NOT NULL CONSTRAINT DF_oficinas_created DEFAULT SYSUTCDATETIME(),
 CONSTRAINT UQ_oficinas_nombre UNIQUE(nombre_key), CONSTRAINT UQ_oficinas_prefijo UNIQUE(prefijo_comprobante),
 CONSTRAINT CK_oficinas_prefijo CHECK(prefijo_comprobante COLLATE Latin1_General_100_CI_AI LIKE '[A-Z][A-Z][A-Z]')
);
IF OBJECT_ID(N'dbo.usuarios','U') IS NULL
CREATE TABLE dbo.usuarios (
 id nvarchar(64) NOT NULL CONSTRAINT PK_usuarios PRIMARY KEY, email nvarchar(320) NOT NULL,
 email_key AS LOWER(LTRIM(RTRIM(email))) PERSISTED, nombre nvarchar(200) NOT NULL,
 rol nvarchar(20) NOT NULL, office_id nvarchar(64) NULL, password_hash nvarchar(255) NOT NULL,
 created_at datetime2(3) NOT NULL CONSTRAINT DF_usuarios_created DEFAULT SYSUTCDATETIME(),
 CONSTRAINT UQ_usuarios_email UNIQUE(email_key), CONSTRAINT FK_usuarios_oficina FOREIGN KEY(office_id) REFERENCES dbo.oficinas(id),
 CONSTRAINT CK_usuarios_rol CHECK(rol IN(N'SuperAdmin',N'Administrador',N'Caja',N'Consultas'))
);
CREATE UNIQUE INDEX IX_usuarios_un_admin ON dbo.usuarios(office_id) WHERE rol=N'Administrador' AND office_id IS NOT NULL;
IF OBJECT_ID(N'dbo.personas','U') IS NULL
CREATE TABLE dbo.personas (
 id nvarchar(64) NOT NULL CONSTRAINT PK_personas PRIMARY KEY, ci nvarchar(30) NOT NULL,
 ci_key AS LOWER(LTRIM(RTRIM(ci))) PERSISTED, nombre nvarchar(200) NOT NULL, created_at datetime2(3) NOT NULL CONSTRAINT DF_personas_created DEFAULT SYSUTCDATETIME(),
 CONSTRAINT UQ_personas_ci UNIQUE(ci_key)
);
IF OBJECT_ID(N'dbo.estudiantes','U') IS NULL
CREATE TABLE dbo.estudiantes (
 id nvarchar(64) NOT NULL CONSTRAINT PK_estudiantes PRIMARY KEY, ci nvarchar(30) NOT NULL,
 ci_key AS LOWER(LTRIM(RTRIM(ci))) PERSISTED, cu nvarchar(50) NOT NULL CONSTRAINT DF_estudiantes_cu DEFAULT N'', cu_key AS LOWER(LTRIM(RTRIM(cu))) PERSISTED,
 nombre nvarchar(200) NOT NULL, gestion int NOT NULL, office_id nvarchar(64) NOT NULL,
 CONSTRAINT FK_estudiantes_oficina FOREIGN KEY(office_id) REFERENCES dbo.oficinas(id), CONSTRAINT CK_estudiantes_gestion CHECK(gestion BETWEEN 1900 AND 9999)
);
CREATE UNIQUE INDEX IX_estudiantes_cu_oficina ON dbo.estudiantes(office_id,cu) WHERE cu<>N'';
IF OBJECT_ID(N'dbo.tipos_pagos','U') IS NULL
CREATE TABLE dbo.tipos_pagos (
 id nvarchar(64) NOT NULL CONSTRAINT PK_tipos_pagos PRIMARY KEY, office_id nvarchar(64) NOT NULL,
 nombre nvarchar(200) NOT NULL, nombre_key AS LOWER(LTRIM(RTRIM(nombre))) PERSISTED, descripcion nvarchar(500) NOT NULL CONSTRAINT DF_tipos_desc DEFAULT N'',
 monto decimal(19,2) NOT NULL, inicio date NOT NULL, fin date NULL,
 CONSTRAINT FK_tipos_oficina FOREIGN KEY(office_id) REFERENCES dbo.oficinas(id), CONSTRAINT UQ_tipos_nombre UNIQUE(office_id,nombre_key),
 CONSTRAINT CK_tipos_monto CHECK(monto>=0), CONSTRAINT CK_tipos_fechas CHECK(fin IS NULL OR fin>=inicio)
);
IF OBJECT_ID(N'dbo.ambientes','U') IS NULL
CREATE TABLE dbo.ambientes (
 id nvarchar(64) NOT NULL CONSTRAINT PK_ambientes PRIMARY KEY, office_id nvarchar(64) NOT NULL,
 nombre nvarchar(120) NOT NULL, nombre_key AS LOWER(LTRIM(RTRIM(nombre))) PERSISTED, descripcion nvarchar(500) NOT NULL CONSTRAINT DF_amb_desc DEFAULT N'',
 created_at datetime2(3) NOT NULL CONSTRAINT DF_amb_created DEFAULT SYSUTCDATETIME(),
 CONSTRAINT FK_amb_oficina FOREIGN KEY(office_id) REFERENCES dbo.oficinas(id), CONSTRAINT UQ_amb_nombre UNIQUE(office_id,nombre_key)
);
IF OBJECT_ID(N'ambiente_horarios','U') IS NULL
CREATE TABLE dbo.ambiente_horarios (
 id bigint IDENTITY CONSTRAINT PK_amb_hor PRIMARY KEY, ambiente_id nvarchar(64) NOT NULL, dia tinyint NOT NULL, desde time(0) NOT NULL, hasta time(0) NOT NULL,
 CONSTRAINT FK_amb_hor_amb FOREIGN KEY(ambiente_id) REFERENCES dbo.ambientes(id), CONSTRAINT CK_amb_hor_dia CHECK(dia BETWEEN 0 AND 6), CONSTRAINT CK_amb_hor_range CHECK(desde<hasta)
);
IF OBJECT_ID(N'tarifas_ambientes','U') IS NULL
CREATE TABLE dbo.tarifas_ambientes (
 id nvarchar(64) NOT NULL CONSTRAINT PK_tarifas PRIMARY KEY, ambiente_id nvarchar(64) NOT NULL, office_id nvarchar(64) NOT NULL,
 nombre nvarchar(120) NOT NULL, nombre_key AS LOWER(LTRIM(RTRIM(nombre))) PERSISTED, modalidad nvarchar(20) NOT NULL, monto decimal(19,2) NOT NULL,
 descripcion nvarchar(500) NOT NULL CONSTRAINT DF_tar_desc DEFAULT N'', desde time(0) NULL, hasta time(0) NULL,
 CONSTRAINT FK_tar_amb FOREIGN KEY(ambiente_id) REFERENCES dbo.ambientes(id), CONSTRAINT FK_tar_oficina FOREIGN KEY(office_id) REFERENCES dbo.oficinas(id),
 CONSTRAINT UQ_tar_nombre UNIQUE(ambiente_id,nombre_key), CONSTRAINT CK_tar_modalidad CHECK(modalidad IN(N'hora',N'manana',N'tarde',N'dia',N'actividad')), CONSTRAINT CK_tar_monto CHECK(monto>0), CONSTRAINT CK_tar_horas CHECK((modalidad IN(N'manana',N'tarde') AND desde IS NOT NULL AND hasta IS NOT NULL AND desde<hasta) OR (modalidad NOT IN(N'manana',N'tarde') AND desde IS NULL AND hasta IS NULL))
);
IF OBJECT_ID(N'pagos','U') IS NULL
CREATE TABLE dbo.pagos (
 id nvarchar(64) NOT NULL CONSTRAINT PK_pagos PRIMARY KEY, office_id nvarchar(64) NOT NULL, id_estudiante nvarchar(64) NOT NULL,
 fecha_pago date NOT NULL, gestion int NOT NULL, cod_comprobante nvarchar(30) NULL, prefijo_comprobante char(3) NULL, estado nvarchar(20) NOT NULL CONSTRAINT DF_pagos_estado DEFAULT N'borrador',
 monto decimal(19,2) NOT NULL CONSTRAINT DF_pagos_monto DEFAULT 0, total decimal(19,2) NOT NULL CONSTRAINT DF_pagos_total DEFAULT 0, anulado bit NOT NULL CONSTRAINT DF_pagos_anulado DEFAULT 0,
 anulado_at datetime2(3) NULL, anulado_by nvarchar(64) NULL, created_at datetime2(3) NOT NULL CONSTRAINT DF_pagos_created DEFAULT SYSUTCDATETIME(), created_by nvarchar(64) NULL, edited_at datetime2(3) NULL, edited_by nvarchar(64) NULL,
 CONSTRAINT FK_pagos_oficina FOREIGN KEY(office_id) REFERENCES dbo.oficinas(id), CONSTRAINT FK_pagos_estudiante FOREIGN KEY(id_estudiante) REFERENCES dbo.estudiantes(id), CONSTRAINT CK_pagos_estado CHECK(estado IN(N'borrador',N'emitido',N'finalizado')), CONSTRAINT CK_pagos_money CHECK(monto>=0 AND total>=0)
);
CREATE UNIQUE INDEX IX_pagos_recibo ON dbo.pagos(office_id,gestion,cod_comprobante) WHERE cod_comprobante IS NOT NULL;
IF OBJECT_ID(N'pago_items','U') IS NULL
CREATE TABLE dbo.pago_items (
 id nvarchar(64) NOT NULL CONSTRAINT PK_pago_items PRIMARY KEY, pago_id nvarchar(64) NOT NULL, id_tipo_pago nvarchar(64) NOT NULL, cantidad decimal(19,4) NOT NULL, monto decimal(19,2) NOT NULL,
 CONSTRAINT FK_items_pago FOREIGN KEY(pago_id) REFERENCES dbo.pagos(id), CONSTRAINT FK_items_tipo FOREIGN KEY(id_tipo_pago) REFERENCES dbo.tipos_pagos(id), CONSTRAINT CK_items_positive CHECK(cantidad>0 AND monto>=0)
);
IF OBJECT_ID(N'alquileres','U') IS NULL
CREATE TABLE dbo.alquileres (
 id nvarchar(64) NOT NULL CONSTRAINT PK_alquileres PRIMARY KEY, office_id nvarchar(64) NOT NULL, ambiente_id nvarchar(64) NOT NULL, tarifa_id nvarchar(64) NOT NULL, fecha date NOT NULL,
 cliente_tipo nvarchar(20) NOT NULL, cliente_id nvarchar(64) NOT NULL, cliente_documento nvarchar(50) NULL, cliente_nombre nvarchar(200) NULL, cliente_ci nvarchar(50) NULL, cliente_cu nvarchar(50) NULL,
 estado nvarchar(20) NOT NULL, total decimal(19,2) NOT NULL, cantidad decimal(19,4) NOT NULL CONSTRAINT DF_alq_cantidad DEFAULT 1, monto decimal(19,2) NOT NULL, gestion int NOT NULL, cod_comprobante nvarchar(30) NULL, prefijo_comprobante char(3) NULL, comprobante_display nvarchar(80) NULL,
 paid_by nvarchar(64) NULL, fecha_pago datetime2(3) NULL, processing_lease_until datetime2(3) NULL, payment_token nvarchar(100) NULL, confirmation_started_at datetime2(3) NULL, processing_started_at datetime2(3) NULL, created_at datetime2(3) NOT NULL CONSTRAINT DF_alq_created DEFAULT SYSUTCDATETIME(),
 CONSTRAINT FK_alq_oficina FOREIGN KEY(office_id) REFERENCES dbo.oficinas(id), CONSTRAINT FK_alq_amb FOREIGN KEY(ambiente_id) REFERENCES dbo.ambientes(id), CONSTRAINT FK_alq_tar FOREIGN KEY(tarifa_id) REFERENCES dbo.tarifas_ambientes(id), CONSTRAINT CK_alq_estado CHECK(estado IN(N'reservado',N'confirmando',N'procesando',N'pagado',N'cancelado')), CONSTRAINT CK_alq_cliente CHECK(cliente_tipo IN(N'persona',N'estudiante'))
);
CREATE UNIQUE INDEX IX_alq_recibo ON dbo.alquileres(office_id,gestion,cod_comprobante) WHERE cod_comprobante IS NOT NULL;
IF OBJECT_ID(N'alquiler_tramos','U') IS NULL
CREATE TABLE dbo.alquiler_tramos (id bigint IDENTITY CONSTRAINT PK_alq_tramos PRIMARY KEY, alquiler_id nvarchar(64) NOT NULL, desde time(0) NOT NULL, hasta time(0) NOT NULL, CONSTRAINT FK_tramos_alq FOREIGN KEY(alquiler_id) REFERENCES dbo.alquileres(id), CONSTRAINT CK_tramos_range CHECK(desde<hasta));
IF OBJECT_ID(N'ambiente_ocupacion','U') IS NULL
CREATE TABLE dbo.ambiente_ocupacion (ambiente_id nvarchar(64) NOT NULL, fecha date NOT NULL, version rowversion, CONSTRAINT PK_amb_ocup PRIMARY KEY(ambiente_id,fecha), CONSTRAINT FK_ocup_amb FOREIGN KEY(ambiente_id) REFERENCES dbo.ambientes(id));
IF OBJECT_ID(N'ocupacion_intervalos','U') IS NULL
CREATE TABLE dbo.ocupacion_intervalos (id bigint IDENTITY CONSTRAINT PK_ocup_int PRIMARY KEY, ambiente_id nvarchar(64) NOT NULL, fecha date NOT NULL, alquiler_id nvarchar(64) NOT NULL, desde time(0) NOT NULL, hasta time(0) NOT NULL, claimed_at datetime2(3) NOT NULL CONSTRAINT DF_ocup_claim DEFAULT SYSUTCDATETIME(), CONSTRAINT FK_int_ocup FOREIGN KEY(ambiente_id,fecha) REFERENCES dbo.ambiente_ocupacion(ambiente_id,fecha), CONSTRAINT FK_int_alq FOREIGN KEY(alquiler_id) REFERENCES dbo.alquileres(id), CONSTRAINT CK_int_range CHECK(desde<hasta));
CREATE INDEX IX_ocup_lookup ON dbo.ocupacion_intervalos(ambiente_id,fecha,desde,hasta);
IF OBJECT_ID(N'alquiler_arrendamientos','U') IS NULL
CREATE TABLE dbo.alquiler_arrendamientos (alquiler_id nvarchar(64) NOT NULL CONSTRAINT PK_alq_lease PRIMARY KEY, lease_until datetime2(3) NOT NULL, token nvarchar(100) NOT NULL, CONSTRAINT FK_lease_alq FOREIGN KEY(alquiler_id) REFERENCES dbo.alquileres(id));
IF OBJECT_ID(N'comprobante_contadores','U') IS NULL
CREATE TABLE dbo.comprobante_contadores (office_id nvarchar(64) NOT NULL, gestion int NOT NULL, siguiente bigint NOT NULL CONSTRAINT DF_counter_next DEFAULT 1, CONSTRAINT PK_contadores PRIMARY KEY(office_id,gestion), CONSTRAINT FK_counter_office FOREIGN KEY(office_id) REFERENCES dbo.oficinas(id));
IF OBJECT_ID(N'comprobante_asignaciones','U') IS NULL
CREATE TABLE dbo.comprobante_asignaciones (office_id nvarchar(64) NOT NULL, gestion int NOT NULL, codigo nvarchar(30) NOT NULL, origen nvarchar(20) NOT NULL, origen_id nvarchar(64) NOT NULL, asignado_at datetime2(3) NOT NULL CONSTRAINT DF_alloc_at DEFAULT SYSUTCDATETIME(), CONSTRAINT PK_asignaciones PRIMARY KEY(office_id,gestion,codigo), CONSTRAINT UQ_alloc_source UNIQUE(origen,origen_id), CONSTRAINT FK_alloc_office FOREIGN KEY(office_id) REFERENCES dbo.oficinas(id));
GO