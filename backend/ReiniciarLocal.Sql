/* DESTRUCTIVO: borra TODOS los datos de ComprobantesDB.
   Ejecutar SOLO en su SQL Server local, con serverSQL.py detenido.
   Después ejecutar Tablas.Sql y arrancar serverSQL.py: se creará únicamente
   el SuperAdmin configurado en ADMIN_EMAIL / ADMIN_NAME / ADMIN_PASSWORD.
   Este archivo NO es ejecutado automáticamente por el servidor.
*/
USE master;
GO
IF DB_ID(N'ComprobantesDB') IS NOT NULL
BEGIN
    ALTER DATABASE ComprobantesDB SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE ComprobantesDB;
END
GO
CREATE DATABASE ComprobantesDB;
GO
