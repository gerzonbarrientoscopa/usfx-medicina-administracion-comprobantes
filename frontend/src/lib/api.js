import axios from "axios";

export const API_URL = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
    const token = localStorage.getItem("token");
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

export function formatApiError(err) {
    const detail = err?.response?.data?.detail;
    if (detail == null) return err?.message || "Error desconocido";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
        return detail
            .map((d) => (d && typeof d.msg === "string" ? d.msg : JSON.stringify(d)))
            .filter(Boolean)
            .join(" | ");
    }
    if (detail && typeof detail.msg === "string") return detail.msg;
    return String(detail);
}

export function formatMoney(n) {
    const v = Number(n || 0);
    return v.toLocaleString("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
