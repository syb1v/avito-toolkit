"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { SearchFormModal } from "@/app/components/search-form-modal";
import type { Account, Search } from "@/lib/api";

export function EditSearchButton({
  search,
  accounts,
}: {
  search: Search;
  accounts: Account[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1 text-xs text-sky-200 transition hover:bg-sky-500/20"
      >
        Редактировать поиск
      </button>
      <SearchFormModal
        open={open}
        search={search}
        accounts={accounts}
        onClose={() => setOpen(false)}
        onSaved={() => router.refresh()}
      />
    </>
  );
}
