import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { IconChevronDown } from "./icons";

export interface SelectOption {
  value: string;
  label: string;
}

/** Combobox with a filterable, scrollable option list. */
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
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const selected = options.find((option) => option.value === value);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return options;
    return options.filter((option) => option.label.toLowerCase().includes(needle));
  }, [options, query]);

  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [open]);

  const openList = () => {
    if (disabled) return;
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
          if (!open) setOpen(true);
        }}
        onKeyDown={onKeyDown}
        onBlur={closeList}
      />
      <span className="combobox__chevron">
        <IconChevronDown size={14} />
      </span>
      {open ? (
        <ul
          className="combobox__list"
          id={listId}
          role="listbox"
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
        </ul>
      ) : null}
    </div>
  );
}
