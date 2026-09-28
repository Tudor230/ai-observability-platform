import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { IconChevronDown } from "./icons";

export interface SelectOption {
  value: string;
  label: string;
}

/** Combobox with a filterable, scrollable option list (native select for scale). */
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
    const onClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const openList = () => {
    setQuery("");
    setHighlight(0);
    setOpen(true);
  };

  const choose = (option: SelectOption) => {
    onChange(option.value);
    setOpen(false);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((current) => Math.min(current + 1, filtered.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = filtered[highlight];
      if (option) choose(option);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div className="combobox" ref={rootRef}>
      {open ? (
        <input
          ref={inputRef}
          className="field__input"
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-label={ariaLabel}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setHighlight(0);
          }}
          onKeyDown={onKeyDown}
          autoComplete="off"
          autoFocus
        />
      ) : (
        <button
          type="button"
          className="field__input combobox__trigger"
          aria-haspopup="listbox"
          aria-expanded="false"
          aria-label={ariaLabel}
          disabled={disabled}
          onClick={openList}
        >
          <span className="truncate">
            {selected ? selected.label : <span className="muted">{placeholder}</span>}
          </span>
          <IconChevronDown size={14} />
        </button>
      )}
      {open ? (
        <ul className="combobox__list" id={listId} role="listbox">
          {filtered.length ? (
            filtered.map((option, index) => (
              <li
                key={option.value}
                role="option"
                aria-selected={option.value === value}
                className="combobox__option"
                data-highlighted={index === highlight}
                onMouseEnter={() => setHighlight(index)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(option)}
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
