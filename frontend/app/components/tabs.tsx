"use client";

import { useState } from "react";

export function Tabs({
  tabs,
  initialId,
}: {
  tabs: { id: string; label: string; content: React.ReactNode }[];
  initialId?: string;
}) {
  const [active, setActive] = useState(initialId ?? tabs[0]?.id ?? "");

  return (
    <div className="flex flex-col gap-6">
      <nav className="flex flex-wrap gap-1 rounded-xl border border-neutral-800 bg-neutral-900/60 p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActive(tab.id)}
            className={`rounded-lg px-3.5 py-1.5 text-sm transition ${
              active === tab.id
                ? "bg-neutral-800 text-neutral-100"
                : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      {tabs.map((tab) => (
        <div key={tab.id} className={active === tab.id ? "flex flex-col gap-6" : "hidden"}>
          {tab.content}
        </div>
      ))}
    </div>
  );
}
