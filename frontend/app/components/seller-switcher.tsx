"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { type Account, fetchAccounts } from "@/lib/api";

export function SellerSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const selected = searchParams.get("seller") ?? "all";

  useEffect(() => {
    fetchAccounts().then(setAccounts);
  }, []);

  const sellers = accounts.filter((account) => account.role === "seller");
  if (sellers.length === 0) return null;

  function change(value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value === "all") params.delete("seller");
    else params.set("seller", value);
    const query = params.toString();
    router.push(`${pathname}${query ? `?${query}` : ""}`);
  }

  return (
    <label className="flex min-w-0 items-center gap-2 text-xs text-neutral-500">
      <span className="hidden sm:inline">Продавец</span>
      <select
        name="seller"
        value={selected}
        onChange={(event) => change(event.target.value)}
        className="max-w-44 rounded-lg border border-neutral-800 bg-neutral-900 px-2.5 py-1.5 text-xs text-neutral-200 outline-none transition hover:border-neutral-700 focus:border-sky-500"
        aria-label="Выбрать продавца"
      >
        <option value="all">Все продавцы</option>
        {sellers.map((account) => (
          <option key={account.id} value={account.id}>
            {account.name}
          </option>
        ))}
      </select>
    </label>
  );
}
