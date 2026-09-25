import { useEffect, useMemo, useState } from "react";
import { apiClient, formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

export function useOfficeScope() {
    const { user } = useAuth();
    const isSuperAdmin = user?.rol === "SuperAdmin";
    const [offices, setOffices] = useState([]);
    const [selectedOfficeId, setSelectedOfficeId] = useState("");

    useEffect(() => {
        if (!isSuperAdmin) return;
        let cancelled = false;
        const load = async () => {
            try {
                const first = await apiClient.get("/oficinas", { params: { pag: 1, tam: 100 } });
                const totalPages = first.data.pages || 1;
                const rest = await Promise.all(
                    Array.from({ length: totalPages - 1 }, (_, index) =>
                        apiClient.get("/oficinas", { params: { pag: index + 2, tam: 100 } }),
                    ),
                );
                if (!cancelled) {
                    setOffices([
                        ...first.data.items,
                        ...rest.flatMap((response) => response.data.items),
                    ]);
                }
            } catch (error) {
                if (!cancelled) toast.error(formatApiError(error));
            }
        };
        load();
        return () => { cancelled = true; };
    }, [isSuperAdmin]);

    const officeId = isSuperAdmin ? selectedOfficeId : (user?.office_id || "");
    const officeName = useMemo(() => {
        if (!isSuperAdmin) return user?.office_nombre || "";
        return offices.find((office) => office.id === selectedOfficeId)?.nombre || "Todas las oficinas";
    }, [isSuperAdmin, offices, selectedOfficeId, user?.office_nombre]);

    return {
        isSuperAdmin,
        offices,
        officeId,
        officeName,
        selectedOfficeId,
        setSelectedOfficeId,
        officeParams: isSuperAdmin && selectedOfficeId ? { office_id: selectedOfficeId } : {},
    };
}