import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";
import { IconChevronDown } from "./icons";

export interface SelectOption {
  value: string;
  label: string;
}

interface Placement {
  left: number;
  width: number;
  maxHeight: number;
  up: boolean;
  top: number;
  bottom: number;
}

/**
 * Combobox with a filterable, scrollable option list.
 *
 * The list renders in a portal with fixed positioning and flips above the
 * input when there is not enough room below (and caps its height to the
 * available viewport), so it is never clipped by page or modal bounds
 * (refinements v2).
 */
export function SearchableSelect({
  value,
  onChange,
  options,
  placeholder = "Select…",
  disabled = false,
  "aria-label": ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  "aria-label"?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const selected = options.find((option) => option.value === value);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return options;
    return options.filter((option) => option.label.toLowerCase().includes(needle));
  }, [options, query]);

  const measure = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const gap = 4;
    const margin = 12;
    const spaceBelow = window.innerHeight - rect.bottom - gap - margin;
    const spaceAbove = rect.top - gap - margin;
    const up = spaceBelow < 200 && spaceAbove > spaceBelow;
    const maxHeight = Math.max(140, Math.min(260, up ? spaceAbove : spaceBelow));
    setPlacement({
      left: rect.left,
      width: rect.width,
      maxHeight,
      up,
      top: rect.bottom + gap,
      bottom: window.innerHeight - rect.top + gap,
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    const onViewportChange = () => measure();
    window.addEventListener("resize", onViewportChange);
    window.addEventListener("scroll", onViewportChange, true);
    return () => {
      window.removeEventListener("resize", onViewportChange);
      window.removeEventListener("scroll", onViewportChange, true);
    };
  }, [open, measure]);

  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target)) return;
      // The list lives in a portal outside the root; clicks inside it are
      // handled by the option's own mousedown.
      if ((target as HTMLElement).closest?.(".combobox__list")) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [open]);

  const openList = () => {
    if (disabled) return;
    measure();
    setQuery("");
    setHighlight(0);
    setOpen(true);
  };

  const closeList = () => {
    setOpen(false);
    setQuery("");
  };

  const choose = (option: SelectOption) => {
    onChange(option.value);
    closeList();
    inputRef.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) openList();
      else setHighlight((current) => Math.min(current + 1, filtered.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = filtered[highlight];
      if (open && option) choose(option);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeList();
    }
  };

  const listStyle: CSSProperties | undefined = placement
    ? {
        position: "fixed",
        left: placement.left,
        width: placement.width,
        maxHeight: placement.maxHeight,
        zIndex: 2000,
        ...(placement.up ? { bottom: placement.bottom } : { top: placement.top }),
      }
    : undefined;

  return (
    <div className="combobox" ref={rootRef}>
      <input
        ref={inputRef}
        className="field__input combobox__input"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-label={ariaLabel}
        value={open ? query : (selected?.label ?? "")}
        placeholder={selected ? selected.label : placeholder}
        disabled={disabled}
        autoComplete="off"
        onFocus={() => {
          if (!open) openList();
        }}
        onClick={() => {
          if (!open) openList();
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setHighlight(0);
          if (!open) openList();
        }}
        onKeyDown={onKeyDown}
        onBlur={closeList}
      />
      <span className="combobox__chevron">
        <IconChevronDown size={14} />
      </span>
      {open && listStyle
        ? createPortal(
            <ul
              className="combobox__list"
              id={listId}
              role="listbox"
              style={listStyle}
              onMouseDown={(event) => event.preventDefault()}
            >
              {filtered.length ? (
                filtered.map((option, index) => (
                  <li
                    key={option.value}
                    role="option"
                    aria-selected={option.value === value}
                    className="combobox__option"
                    data-highlighted={index === highlight}
                    onMouseEnter={() => setHighlight(index)}
                    onMouseDown={() => choose(option)}
                  >
                    {option.label}
                  </li>
                ))
              ) : (
                <li className="combobox__empty">No matches</li>
              )}
            </ul>,
            document.body
          )
        : null}
    </div>
  );
}
