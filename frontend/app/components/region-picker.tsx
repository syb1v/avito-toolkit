"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { REGIONS, regionName } from "@/lib/regions";

export function RegionPicker({
  value,
  onChange,
  emptyLabel = "Все города",
}: {
  value: string[];
  onChange: (next: string[]) => void;
  emptyLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onClick(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const options = useMemo(() => {
    const known = REGIONS.map((region) => ({
      slug: region.slug,
      name: region.name,
    }));
    for (const slug of value) {
      if (!known.some((option) => option.slug === slug)) {
        known.push({ slug, name: `${slug} (текущий)` });
      }
    }
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return known;
    }
    return known.filter(
      (option) =>
        option.name.toLowerCase().includes(normalized) ||
        option.slug.includes(normalized),
    );
  }, [query, value]);

  function toggle(slug: string) {
    onChange(
      value.includes(slug)
        ? value.filter((item) => item !== slug)
        : [...value, slug],
    );
  }

  const summary =
    value.length === 0
      ? emptyLabel
      : value.length <= 2
        ? value.map((slug) => regionName(slug)).join(", ")
        : `${value
            .slice(0, 2)
            .map((slug) => regionName(slug))
            .join(", ")} +${value.length - 2}`;

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className={`flex w-full items-center justify-between gap-2 rounded-lg border bg-neutral-950 px-3 py-2 text-left text-sm transition ${
          open ? "border-sky-500/60" : "border-neutral-800 hover:border-neutral-600"
        }`}
      >
        <span className={value.length === 0 ? "text-neutral-500" : "text-neutral-200"}>
          {summary}
        </span>
        <span className="flex items-center gap-1">
          {value.length > 0 ? (
            <span
              role="button"
              tabIndex={0}
              onClick={(event) => {
                event.stopPropagation();
                onChange([]);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.stopPropagation();
                  onChange([]);
                }
              }}
              className="rounded px-1 text-xs text-neutral-500 hover:text-neutral-200"
              title="Сбросить"
            >
              ✕
            </span>
          ) : null}
          <span className="text-xs text-neutral-500">{open ? "▲" : "▼"}</span>
        </span>
      </button>

      {value.length > 0 ? (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {value.map((slug) => (
            <span
              key={slug}
              className="inline-flex items-center gap-1 rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[11px] text-sky-100"
            >
              {regionName(slug)}
              <button
                type="button"
                onClick={() => toggle(slug)}
                className="text-sky-300/70 hover:text-sky-100"
                title="Убрать"
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      ) : null}

      {open ? (
        <div className="absolute z-30 mt-1 w-full min-w-[280px] rounded-xl border border-neutral-700 bg-neutral-900 p-2 shadow-xl shadow-black/40">
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Поиск города…"
            className="w-full rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-1.5 text-xs text-neutral-200 outline-none placeholder:text-neutral-600 focus:border-sky-500/60"
          />
          <div className="mt-2 flex items-center justify-between px-1 text-[10px] text-neutral-500">
            <span>выбрано: {value.length}</span>
            <span className="flex gap-2">
              <button
                type="button"
                onClick={() => onChange(REGIONS.map((region) => region.slug))}
                className="hover:text-neutral-200"
              >
                все
              </button>
              <button
                type="button"
                onClick={() => onChange([])}
                className="hover:text-neutral-200"
              >
                сбросить
              </button>
            </span>
          </div>
          <div className="mt-1 grid max-h-56 grid-cols-2 gap-0.5 overflow-y-auto pr-1">
            {options.map((option) => {
              const checked = value.includes(option.slug);
              return (
                <label
                  key={option.slug}
                  className={`flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-xs transition ${
                    checked
                      ? "bg-sky-500/10 text-sky-100"
                      : "text-neutral-300 hover:bg-neutral-800"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(option.slug)}
                    className="h-3.5 w-3.5 accent-sky-500"
                  />
                  <span className="truncate">{option.name}</span>
                </label>
              );
            })}
            {options.length === 0 ? (
              <p className="col-span-2 px-2 py-3 text-center text-xs text-neutral-600">
                Ничего не найдено
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
