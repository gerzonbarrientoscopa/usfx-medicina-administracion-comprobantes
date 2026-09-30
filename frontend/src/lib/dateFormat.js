const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})/;
const DISPLAY_DATE = /^(\d{1,2})\/(\d{1,2})\/(\d{4})/;

const isValidDate = (year, month, day) => {
    const candidate = new Date(year, month - 1, day);
    return candidate.getFullYear() === year
        && candidate.getMonth() === month - 1
        && candidate.getDate() === day;
};

export function toISODate(value) {
    if (!value) return "";
    if (value instanceof Date) {
        if (Number.isNaN(value.getTime())) return "";
        const year = value.getFullYear();
        const month = String(value.getMonth() + 1).padStart(2, "0");
        const day = String(value.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    const text = String(value).trim();
    const displayMatch = text.match(DISPLAY_DATE);
    if (displayMatch) {
        const [, dayText, monthText, yearText] = displayMatch;
        const year = Number(yearText);
        const month = Number(monthText);
        const day = Number(dayText);
        if (!isValidDate(year, month, day)) return "";
        return `${yearText}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }

    const isoMatch = text.match(ISO_DATE);
    if (isoMatch) {
        const [, yearText, monthText, dayText] = isoMatch;
        if (!isValidDate(Number(yearText), Number(monthText), Number(dayText))) return "";
        return `${yearText}-${monthText}-${dayText}`;
    }
    return "";
}

export function formatDate(value) {
    const iso = toISODate(value);
    if (!iso) return value ? String(value) : "";
    const [year, month, day] = iso.split("-");
    return `${day}/${month}/${year}`;
}