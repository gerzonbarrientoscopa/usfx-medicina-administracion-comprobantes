/* Comprobantes USFX - SQL Server schema for a NEW database.
   Run with sqlcmd (GO separators are intentional). This script never drops
   existing data: remove the old database separately before installing this
   incompatible INT IDENTITY schema. Receipt numbers are allocated
   through comprobante_asignaciones (the service locks that row); the unique
   filtered indexes on both source tables are a second line of defence.
   Interval claims cannot be expressed safely by a normal
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
IF EXISTS(SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.oficinas')
          AND name=N'id' AND (system_type_id<>56 OR is_identity=0))
    THROW 50001, 'Esquema antiguo: recree ComprobantesDB antes de ejecutar este script. No se migran UUID.', 1;
GO

IF OBJECT_ID(N'dbo.estudiantes','U') IS NOT NULL OR OBJECT_ID(N'dbo.personas','U') IS NOT NULL
 OR EXISTS(SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.usuarios') AND name=N'id' AND is_identity=0)
    THROW 50002, 'Esquema incompatible con Clientes. Use una base nueva o ReiniciarLocal.Sql antes de instalar Tablas.Sql.', 1;
GO

IF OBJECT_ID(N'dbo.oficinas','U') IS NULL
CREATE TABLE dbo.oficinas (
  id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_oficinas PRIMARY KEY,
 nombre nvarchar(200) NOT NULL, nombre_key AS LOWER(LTRIM(RTRIM(nombre))) PERSISTED,
 prefijo_comprobante char(3) NOT NULL, suboficina nvarchar(100) NOT NULL CONSTRAINT DF_oficinas_sub DEFAULT N'',
 activa bit NOT NULL CONSTRAINT DF_oficinas_activa DEFAULT 1, created_at datetime2(3) NOT NULL CONSTRAINT DF_oficinas_created DEFAULT SYSUTCDATETIME(),
 CONSTRAINT UQ_oficinas_nombre UNIQUE(nombre_key), CONSTRAINT UQ_oficinas_prefijo UNIQUE(prefijo_comprobante),
 CONSTRAINT CK_oficinas_prefijo CHECK(prefijo_comprobante COLLATE Latin1_General_100_CI_AI LIKE '[A-Z][A-Z][A-Z]')
);
IF OBJECT_ID(N'dbo.usuarios','U') IS NULL
CREATE TABLE dbo.usuarios (
  id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_usuarios PRIMARY KEY, codigo char(3) NOT NULL CONSTRAINT UQ_usuarios_codigo UNIQUE, email nvarchar(320) NOT NULL,
 email_key AS LOWER(LTRIM(RTRIM(email))) PERSISTED, nombre nvarchar(200) NOT NULL,
  rol nvarchar(20) NOT NULL, id_oficina int NULL, password_hash nvarchar(255) NOT NULL,
 created_at datetime2(3) NOT NULL CONSTRAINT DF_usuarios_created DEFAULT SYSUTCDATETIME(),
  CONSTRAINT UQ_usuarios_email UNIQUE(email_key), CONSTRAINT FK_usuarios_oficina FOREIGN KEY(id_oficina) REFERENCES dbo.oficinas(id),
  CONSTRAINT CK_usuarios_rol CHECK(rol IN(N'SuperAdmin',N'Administrador',N'Caja',N'Consultas')),
    CONSTRAINT CK_usuarios_codigo CHECK(codigo COLLATE Latin1_General_100_BIN2 LIKE '[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]'),
   CONSTRAINT CK_usuarios_superadmin CHECK((codigo='000' AND rol=N'SuperAdmin') OR (codigo<>'000' AND rol<>N'SuperAdmin'))
);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.usuarios') AND name=N'IX_usuarios_un_admin')
CREATE UNIQUE INDEX IX_usuarios_un_admin ON dbo.usuarios(id_oficina) WHERE rol=N'Administrador' AND id_oficina IS NOT NULL;
IF OBJECT_ID(N'dbo.clientes','U') IS NULL
CREATE TABLE dbo.clientes (
 id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_clientes PRIMARY KEY,
 ci nvarchar(30) NOT NULL CONSTRAINT DF_clientes_ci DEFAULT N'',
 ci_key AS LOWER(LTRIM(RTRIM(ci))) PERSISTED,
 cu nvarchar(50) NOT NULL CONSTRAINT DF_clientes_cu DEFAULT N'',
 cu_key AS LOWER(LTRIM(RTRIM(cu))) PERSISTED,
 nombre nvarchar(200) NOT NULL,
 CONSTRAINT CK_clientes_identificador CHECK(ci<>N'' OR cu<>N'')
);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.clientes') AND name=N'IX_clientes_ci')
CREATE UNIQUE INDEX IX_clientes_ci ON dbo.clientes(ci_key) WHERE ci<>N'';
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.clientes') AND name=N'IX_clientes_cu')
CREATE UNIQUE INDEX IX_clientes_cu ON dbo.clientes(cu_key) WHERE cu<>N'';
IF OBJECT_ID(N'dbo.tipos_pagos','U') IS NULL
CREATE TABLE dbo.tipos_pagos (
  id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_tipos_pagos PRIMARY KEY, id_oficina int NOT NULL,
 nombre nvarchar(200) NOT NULL, nombre_key AS LOWER(LTRIM(RTRIM(nombre))) PERSISTED, descripcion nvarchar(500) NOT NULL CONSTRAINT DF_tipos_desc DEFAULT N'',
 monto decimal(19,2) NOT NULL, inicio date NOT NULL, fin date NULL,
  CONSTRAINT FK_tipos_oficina FOREIGN KEY(id_oficina) REFERENCES dbo.oficinas(id), CONSTRAINT UQ_tipos_nombre UNIQUE(id_oficina,nombre_key),
 CONSTRAINT CK_tipos_monto CHECK(monto>=0), CONSTRAINT CK_tipos_fechas CHECK(fin IS NULL OR fin>=inicio)
);
IF OBJECT_ID(N'dbo.ambientes','U') IS NULL
CREATE TABLE dbo.ambientes (
  id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_ambientes PRIMARY KEY, id_oficina int NOT NULL,
 nombre nvarchar(120) NOT NULL, nombre_key AS LOWER(LTRIM(RTRIM(nombre))) PERSISTED, descripcion nvarchar(500) NOT NULL CONSTRAINT DF_amb_desc DEFAULT N'',
 created_at datetime2(3) NOT NULL CONSTRAINT DF_amb_created DEFAULT SYSUTCDATETIME(),
  CONSTRAINT FK_amb_oficina FOREIGN KEY(id_oficina) REFERENCES dbo.oficinas(id), CONSTRAINT UQ_amb_nombre UNIQUE(id_oficina,nombre_key)
);
IF OBJECT_ID(N'ambiente_horarios','U') IS NULL
CREATE TABLE dbo.ambiente_horarios (
  id int IDENTITY(1,1) CONSTRAINT PK_amb_hor PRIMARY KEY, id_ambiente int NOT NULL, dia tinyint NOT NULL, desde time(0) NOT NULL, hasta time(0) NOT NULL,
  CONSTRAINT FK_amb_hor_amb FOREIGN KEY(id_ambiente) REFERENCES dbo.ambientes(id), CONSTRAINT CK_amb_hor_dia CHECK(dia BETWEEN 0 AND 6), CONSTRAINT CK_amb_hor_range CHECK(desde<hasta)
);
IF OBJECT_ID(N'ambiente_turnos','U') IS NULL
CREATE TABLE dbo.ambiente_turnos (
  id_ambiente int NOT NULL, turno nvarchar(10) NOT NULL, desde time(0) NOT NULL, hasta time(0) NOT NULL,
  CONSTRAINT PK_amb_turnos PRIMARY KEY(id_ambiente,turno),
  CONSTRAINT FK_amb_turnos_amb FOREIGN KEY(id_ambiente) REFERENCES dbo.ambientes(id),
  CONSTRAINT CK_amb_turnos_tipo CHECK(turno IN(N'manana',N'tarde',N'noche')),
  CONSTRAINT CK_amb_turnos_range CHECK(desde<hasta)
);
IF OBJECT_ID(N'tarifas_ambientes','U') IS NULL
CREATE TABLE dbo.tarifas_ambientes (
  id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_tarifas PRIMARY KEY, id_ambiente int NOT NULL, id_oficina int NOT NULL,
 nombre nvarchar(120) NOT NULL, nombre_key AS LOWER(LTRIM(RTRIM(nombre))) PERSISTED, modalidad nvarchar(20) NOT NULL, monto decimal(19,2) NOT NULL,
  descripcion nvarchar(500) NOT NULL CONSTRAINT DF_tar_desc DEFAULT N'', desde time(0) NULL, hasta time(0) NULL,
  created_at datetime2(3) NOT NULL CONSTRAINT DF_tar_created DEFAULT SYSUTCDATETIME(),
  CONSTRAINT FK_tar_amb FOREIGN KEY(id_ambiente) REFERENCES dbo.ambientes(id), CONSTRAINT FK_tar_oficina FOREIGN KEY(id_oficina) REFERENCES dbo.oficinas(id),
   CONSTRAINT UQ_tar_nombre UNIQUE(id_ambiente,nombre_key), CONSTRAINT CK_tar_modalidad CHECK(modalidad IN(N'hora',N'manana',N'tarde',N'noche',N'dia',N'actividad')), CONSTRAINT CK_tar_monto CHECK(monto>0), CONSTRAINT CK_tar_horas CHECK((modalidad IN(N'manana',N'tarde',N'noche') AND desde IS NOT NULL AND hasta IS NOT NULL AND desde<hasta) OR (modalidad NOT IN(N'manana',N'tarde',N'noche') AND desde IS NULL AND hasta IS NULL))
);
IF OBJECT_ID(N'dbo.tarifas_ambientes','U') IS NOT NULL
BEGIN
  IF NOT EXISTS(SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.tarifas_ambientes') AND name=N'CK_tar_modalidad' AND definition LIKE N'%noche%')
  BEGIN
    IF EXISTS(SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.tarifas_ambientes') AND name=N'CK_tar_modalidad')
      ALTER TABLE dbo.tarifas_ambientes DROP CONSTRAINT CK_tar_modalidad;
    ALTER TABLE dbo.tarifas_ambientes ADD CONSTRAINT CK_tar_modalidad
      CHECK(modalidad IN(N'hora',N'manana',N'tarde',N'noche',N'dia',N'actividad'));
  END
  IF NOT EXISTS(SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.tarifas_ambientes') AND name=N'CK_tar_horas' AND definition LIKE N'%noche%')
  BEGIN
    IF EXISTS(SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.tarifas_ambientes') AND name=N'CK_tar_horas')
      ALTER TABLE dbo.tarifas_ambientes DROP CONSTRAINT CK_tar_horas;
    ALTER TABLE dbo.tarifas_ambientes ADD CONSTRAINT CK_tar_horas
      CHECK((modalidad IN(N'manana',N'tarde',N'noche') AND desde IS NOT NULL AND hasta IS NOT NULL AND desde<hasta) OR (modalidad NOT IN(N'manana',N'tarde',N'noche') AND desde IS NULL AND hasta IS NULL));
  END
END
IF OBJECT_ID(N'pagos','U') IS NULL
CREATE TABLE dbo.pagos (
  id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_pagos PRIMARY KEY, id_oficina int NOT NULL, id_cliente int NOT NULL,
 fecha_pago date NOT NULL, gestion int NOT NULL, cod_comprobante nvarchar(30) NULL, prefijo_comprobante char(3) NULL, estado nvarchar(20) NOT NULL CONSTRAINT DF_pagos_estado DEFAULT N'borrador',
  monto decimal(19,2) NOT NULL CONSTRAINT DF_pagos_monto DEFAULT 0, total decimal(19,2) NOT NULL CONSTRAINT DF_pagos_total DEFAULT 0,
   id_tipo_pago int NULL, cantidad decimal(19,4) NULL, anulado bit NOT NULL CONSTRAINT DF_pagos_anulado DEFAULT 0,
  anulado_at datetime2(3) NULL, anulado_by int NULL, created_at datetime2(3) NOT NULL CONSTRAINT DF_pagos_created DEFAULT SYSUTCDATETIME(), created_by int NULL, edited_at datetime2(3) NULL, edited_by int NULL,
  CONSTRAINT FK_pagos_oficina FOREIGN KEY(id_oficina) REFERENCES dbo.oficinas(id), CONSTRAINT FK_pagos_cliente FOREIGN KEY(id_cliente) REFERENCES dbo.clientes(id), CONSTRAINT CK_pagos_estado CHECK(estado IN(N'borrador',N'emitido',N'finalizado')), CONSTRAINT CK_pagos_money CHECK(monto>=0 AND total>=0)
);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.pagos') AND name=N'IX_pagos_recibo')
CREATE UNIQUE INDEX IX_pagos_recibo ON dbo.pagos(id_oficina,gestion,cod_comprobante) WHERE cod_comprobante IS NOT NULL;
IF OBJECT_ID(N'pago_items','U') IS NULL
CREATE TABLE dbo.pago_items (
   id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_pago_items PRIMARY KEY, id_pago int NOT NULL, id_tipo_pago int NOT NULL,
  tipo_pago_nombre nvarchar(200) NULL, cantidad decimal(19,4) NOT NULL, monto decimal(19,2) NOT NULL, total decimal(19,2) NULL,
   CONSTRAINT FK_items_pago FOREIGN KEY(id_pago) REFERENCES dbo.pagos(id), CONSTRAINT CK_items_positive CHECK(cantidad>0 AND monto>=0)
);
IF OBJECT_ID(N'alquileres','U') IS NULL
CREATE TABLE dbo.alquileres (
  id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_alquileres PRIMARY KEY, id_oficina int NOT NULL, id_ambiente int NOT NULL, id_tarifa int NOT NULL, fecha date NOT NULL,
  id_cliente int NOT NULL, nombre_cliente nvarchar(200) NULL, ci_cliente nvarchar(50) NULL, cu_cliente nvarchar(50) NULL,
  estado nvarchar(20) NOT NULL, total decimal(19,2) NOT NULL, cantidad decimal(19,4) NOT NULL CONSTRAINT DF_alq_cantidad DEFAULT 1, monto decimal(19,2) NOT NULL, gestion int NOT NULL, cod_comprobante nvarchar(30) NULL, prefijo_comprobante char(3) NULL,
  registrado_por int NULL, fecha_pago datetime2(3) NULL, confirmation_started_at datetime2(3) NULL, created_at datetime2(3) NOT NULL CONSTRAINT DF_alq_created DEFAULT SYSUTCDATETIME(),
   CONSTRAINT FK_alq_oficina FOREIGN KEY(id_oficina) REFERENCES dbo.oficinas(id), CONSTRAINT CK_alq_estado CHECK(estado IN(N'reservado',N'confirmando',N'pagado',N'cancelado')), CONSTRAINT FK_alq_cliente FOREIGN KEY(id_cliente) REFERENCES dbo.clientes(id)
);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.alquileres') AND name=N'IX_alq_recibo')
CREATE UNIQUE INDEX IX_alq_recibo ON dbo.alquileres(id_oficina,gestion,cod_comprobante) WHERE cod_comprobante IS NOT NULL;
IF OBJECT_ID(N'alquiler_intervalos','U') IS NULL
CREATE TABLE dbo.alquiler_intervalos (id int IDENTITY(1,1) CONSTRAINT PK_alq_intervalos PRIMARY KEY, alquiler_id int NOT NULL, desde time(0) NOT NULL, hasta time(0) NOT NULL, CONSTRAINT FK_intervalos_alq FOREIGN KEY(alquiler_id) REFERENCES dbo.alquileres(id), CONSTRAINT CK_intervalos_range CHECK(desde<hasta));
IF OBJECT_ID(N'ambiente_ocupacion','U') IS NULL
CREATE TABLE dbo.ambiente_ocupacion (id_ambiente int NOT NULL, fecha date NOT NULL, version rowversion, CONSTRAINT PK_amb_ocup PRIMARY KEY(id_ambiente,fecha), CONSTRAINT FK_ocup_amb FOREIGN KEY(id_ambiente) REFERENCES dbo.ambientes(id));
IF OBJECT_ID(N'ocupacion_intervalos','U') IS NULL
CREATE TABLE dbo.ocupacion_intervalos (id int IDENTITY(1,1) CONSTRAINT PK_ocup_int PRIMARY KEY, id_ambiente int NOT NULL, fecha date NOT NULL, alquiler_id int NOT NULL, desde time(0) NOT NULL, hasta time(0) NOT NULL, reservado_en datetime2(3) NOT NULL CONSTRAINT DF_ocup_claim DEFAULT SYSUTCDATETIME(), CONSTRAINT FK_int_ocup FOREIGN KEY(id_ambiente,fecha) REFERENCES dbo.ambiente_ocupacion(id_ambiente,fecha), CONSTRAINT FK_int_alq FOREIGN KEY(alquiler_id) REFERENCES dbo.alquileres(id), CONSTRAINT CK_int_range CHECK(desde<hasta));
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.ocupacion_intervalos') AND name=N'IX_ocup_lookup')
CREATE INDEX IX_ocup_lookup ON dbo.ocupacion_intervalos(id_ambiente,fecha,desde,hasta);
IF OBJECT_ID(N'comprobante_contadores','U') IS NULL
CREATE TABLE dbo.comprobante_contadores (id_oficina int NOT NULL, gestion int NOT NULL, siguiente bigint NOT NULL CONSTRAINT DF_counter_next DEFAULT 1, CONSTRAINT PK_contadores PRIMARY KEY(id_oficina,gestion), CONSTRAINT FK_counter_office FOREIGN KEY(id_oficina) REFERENCES dbo.oficinas(id));
IF OBJECT_ID(N'comprobante_asignaciones','U') IS NULL
CREATE TABLE dbo.comprobante_asignaciones (id_oficina int NOT NULL, gestion int NOT NULL, codigo nvarchar(30) NOT NULL, origen nvarchar(20) NOT NULL, origen_id int NOT NULL, asignado_at datetime2(3) NOT NULL CONSTRAINT DF_alloc_at DEFAULT SYSUTCDATETIME(), CONSTRAINT PK_asignaciones PRIMARY KEY(id_oficina,gestion,codigo), CONSTRAINT UQ_alloc_source UNIQUE(origen,origen_id), CONSTRAINT FK_alloc_office FOREIGN KEY(id_oficina) REFERENCES dbo.oficinas(id));
GO