import { formatDate, toISODate } from "./dateFormat";

test("formats ISO dates as zero-padded day/month/year", () => {
    expect(formatDate("2026-09-03")).toBe("03/09/2026");
});

test("accepts display-formatted dates and timestamps", () => {
    expect(formatDate("03/09/2026 14:30:00")).toBe("03/09/2026");
    expect(toISODate("03/09/2026")).toBe("2026-09-03");
    expect(toISODate("2026-09-03T14:30:00Z")).toBe("2026-09-03");
});

test("rejects invalid dates for API date inputs", () => {
    expect(toISODate("31/02/2026")).toBe("");
    expect(toISODate("not a date")).toBe("");
});