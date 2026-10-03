"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { REGIONS, regionName } from "@/lib/regions";

export function RegionFilter({
  current,
  counts,
}: {
  current: string | null;
  counts: Record<string, number>;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const options = Object.keys(counts)
    .map((slug) => ({ slug, name: regionName(slug), count: counts[slug] ?? 0 }))
    .sort((left, right) => right.count - left.count);
  const knownSlugs = new Set(options.map((option) => option.slug));
  for (const region of REGIONS) {
    if (counts[region.slug] && !knownSlugs.has(region.slug)) {
      options.push({ slug: region.slug, name: region.name, count: counts[region.slug] });
    }
  }

  function change(value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) {
      next.set("region", value);
    } else {
      next.delete("region");
    }
    const suffix = next.toString();
    router.push(suffix ? `${pathname}?${suffix}` : pathname);
  }

  if (options.length === 0 && !current) {
    return null;
  }

  return (
    <label className="flex items-center gap-2 text-xs text-neutral-500">
      город:
      <select
        value={current ?? ""}
        onChange={(event) => change(event.target.value)}
        className="rounded-lg border border-neutral-800 bg-neutral-950 px-2 py-1 text-xs text-neutral-200 outline-none focus:border-sky-500/60"
      >
        <option value="">все города</option>
        {options.map((option) => (
          <option key={option.slug} value={option.slug}>
            {option.name} ({option.count})
          </option>
        ))}
      </select>
    </label>
  );
}
