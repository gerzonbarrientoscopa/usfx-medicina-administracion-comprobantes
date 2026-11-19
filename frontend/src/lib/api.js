import axios from "axios";

const API_URL = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Interceptor de Peticiones (Inyección de Token)
apiClient.interceptors.request.use(  
  (config) => {    
    const token = localStorage.getItem("token");    
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// Interceptor de Respuestas unificado con formatApiError
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Reutiliza la lógica avanzada de formatApiError para inyectar el mensaje amigable
    error.friendlyMessage = formatApiError(error);
    return Promise.reject(error);
  },
);

export function formatApiError(err) {
  const detail = err?.response?.data?.detail;
  // 1. Si no hay respuesta del servidor (Error de red / Servidor apagado)
  if (detail == null) {
    return err?.message || "Error de conexión con el servidor";
  }
  // 2. Si es un error personalizado de HTTPException (String directo)
  if (typeof detail === "string") return detail;
  // 3. Si es un error de validación de FastAPI / Pydantic (Array)
  if (Array.isArray(detail)) {
    return detail
      .map((errObj) => {
        if (!errObj || typeof errObj.msg !== "string")
          return JSON.stringify(errObj);
        // Opcional: Traducir mensajes genéricos de Pydantic
        if (errObj.msg === "Field required") return "Este campo es obligatorio";
        if (errObj.msg.includes("should be a valid"))
          return "El formato de este campo no es válido";
        return errObj.msg;
      })
      .filter(Boolean)
      .join(" | ");
  }
  // 4. Caso de respaldo por si el objeto detail tiene otra estructura
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export function formatMoney(n) {
    const v = Number(n || 0);
    return v.toLocaleString("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
