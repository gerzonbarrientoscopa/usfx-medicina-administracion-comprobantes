import React, { useEffect, useId, useRef, useState } from "react";
import { es } from "date-fns/locale";
import { CalendarDays } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { formatDate, parseDateInput, toISODate } from "@/lib/dateFormat";

const asLocalDate = (value) => {
    const iso = toISODate(value);
    if (!iso) return undefined;
    const [year, month, day] = iso.split("-").map(Number);
    return new Date(year, month - 1, day, 12);
};

export function DateInput({
    value = "",
    onValueChange,
    onValidityChange,
    className,
    disabled = false,
    ...inputProps
}) {
    const [draft, setDraft] = useState(() => formatDate(value));
    const [calendarOpen, setCalendarOpen] = useState(false);
    const generatedId = useId();
    const lastPublishedValue = useRef(value || "");
    const selectedDate = asLocalDate(value);
    const parsed = parseDateInput(draft);
    const invalid = !parsed.valid;
    const inputId = inputProps.id || generatedId;

    useEffect(() => {
        const nextValue = value || "";
        if (nextValue !== lastPublishedValue.current) {
            setDraft(formatDate(nextValue));
            lastPublishedValue.current = nextValue;
            onValidityChange?.(true);
        }
    }, [value, onValidityChange]);

    const publish = (nextValue, valid) => {
        lastPublishedValue.current = nextValue;
        onValueChange?.(nextValue);
        onValidityChange?.(valid);
    };

    const handleTextChange = (event) => {
        const nextDraft = event.target.value;
        const result = parseDateInput(nextDraft);
        setDraft(nextDraft);
        publish(result.valid ? result.iso : "", result.valid);
    };

    const handleBlur = () => {
        if (!parsed.valid) return;
        const displayValue = formatDate(parsed.iso);
        setDraft(displayValue);
        publish(parsed.iso, true);
    };

    const handleCalendarSelect = (day) => {
        if (!day) return;
        const iso = toISODate(day);
        setDraft(formatDate(iso));
        publish(iso, true);
        setCalendarOpen(false);
    };

    const errorId = `${inputId}-format-error`;

    return (
        <div className="space-y-1">
            <div className="relative">
                <Input
                    {...inputProps}
                    id={inputId}
                    type="text"
                    inputMode="numeric"
                    placeholder="dd/mm/aaaa"
                    autoComplete="off"
                    value={draft}
                    disabled={disabled}
                    onChange={handleTextChange}
                    onBlur={handleBlur}
                    aria-invalid={invalid || undefined}
                    aria-describedby={invalid ? errorId : inputProps["aria-describedby"]}
                    className={cn("pr-10", className)}
                />
                <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
                    <PopoverTrigger asChild>
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            disabled={disabled}
                            aria-label="Elegir fecha"
                            className="absolute right-0 top-0 h-full w-10 rounded-l-none text-[color:var(--institution-muted)]"
                        >
                            <CalendarDays size={16} />
                        </Button>
                    </PopoverTrigger>
                    <PopoverContent align="end" className="w-auto p-0">
                        <Calendar
                            mode="single"
                            locale={es}
                            selected={selectedDate}
                            defaultMonth={selectedDate}
                            onSelect={handleCalendarSelect}
                            initialFocus
                        />
                    </PopoverContent>
                </Popover>
            </div>
            {invalid && (
                <p id={errorId} className="text-xs text-destructive" role="alert">
                    Ingrese una fecha válida en formato dd/mm/aaaa.
                </p>
            )}
        </div>
    );
}
