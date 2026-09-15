import type { ReactNode } from "react";

export interface Tab<T extends string> {
  id: T;
  label: string;
  counter?: number;
}

export function Tabs<T extends string>({
  tabs,
  selected,
  onSelect,
  children,
}: {
  tabs: readonly Tab<T>[];
  selected: T;
  onSelect: (id: T) => void;
  children: ReactNode;
}) {
  return (
    <div className="tabs">
      <div className="tab-list" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            className="tab"
            aria-selected={tab.id === selected}
            onClick={() => onSelect(tab.id)}
          >
            {tab.label}
            {tab.counter !== undefined ? (
              <span className="tab__counter">{tab.counter}</span>
            ) : null}
          </button>
        ))}
      </div>
      <div className="tab-panel" role="tabpanel">
        {children}
      </div>
    </div>
  );
}
