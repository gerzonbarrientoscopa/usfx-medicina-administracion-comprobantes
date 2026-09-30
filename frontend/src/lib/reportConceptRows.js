export function reportConceptRows(pago) {
    const items = Array.isArray(pago?.items) && pago.items.length
        ? pago.items
        : !pago?.id_tipo_pago && !pago?.tipo_pago_nombre
            ? []
            : [{
                id_tipo_pago: pago.id_tipo_pago,
                tipo_pago_nombre: pago.tipo_pago_nombre || "",
                cantidad: pago.cantidad,
                monto: pago.monto,
                total: pago.total,
            }];

    const concepts = items.length ? items : [null];
    return concepts.map((item, index) => {
        const amount = item
            ? item.total ?? (
                item.cantidad != null && item.monto != null
                    ? Number(item.cantidad) * Number(item.monto)
                    : 0
            )
            : pago?.total ?? 0;
        return { item, index, amount };
    });
}