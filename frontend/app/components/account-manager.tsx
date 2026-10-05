"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useConfirm } from "@/app/components/confirm";
import { InfoHint } from "@/app/components/info-hint";
import { Modal } from "@/app/components/modal";
import { useToast } from "@/app/components/toast";
import {
  type Account,
  checkAccountClient,
  createAccountClient,
  deleteAccountClient,
  fetchAccounts,
  fetchProxiesClient,
  updateAccountClient,
  uploadAccountCookiesClient,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

export function AccountManager({ initial }: { initial: Account[] }) {
  const router = useRouter();
  const toast = useToast();
  const confirm = useConfirm();
  const [items, setItems] = useState(initial);
  const [addOpen, setAddOpen] = useState(false);
  const [addName, setAddName] = useState("");
  const [addNotes, setAddNotes] = useState("");
  const [addRole, setAddRole] = useState<"searcher" | "seller">("searcher");
  const [addProxy, setAddProxy] = useState("");
  const [cookieFor, setCookieFor] = useState<Account | null>(null);
  const [cookieText, setCookieText] = useState("");
  const [fresh, setFresh] = useState(true);
  const [proxyFor, setProxyFor] = useState<Account | null>(null);
  const [proxyChoice, setProxyChoice] = useState("");
  const [proxyLabels, setProxyLabels] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchProxiesClient().then((status) => {
      if (!cancelled) {
        setProxyLabels((status?.entries ?? []).map((entry) => entry.label));
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function refresh() {
    setItems(await fetchAccounts());
    router.refresh();
  }

  async function add() {
    if (!addName.trim()) {
      toast.push("error", "Укажите название аккаунта");
      return;
    }
    setBusy("add");
    const result = await createAccountClient({
      name: addName.trim(),
      notes: addNotes.trim() || null,
      role: addRole,
      proxy_label: addProxy || null,
    });
    setBusy(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    setAddName("");
    setAddNotes("");
    setAddProxy("");
    setAddOpen(false);
    toast.push("success", "Аккаунт создан — залейте cookies");
    await refresh();
  }

  async function check(account: Account) {
    setBusy(account.id);
    const result = await checkAccountClient(account.id);
    if (!result.ok) {
      setBusy(null);
      toast.push("error", result.error);
      return;
    }
    if (result.data?.status === "cooldown") {
      setBusy(null);
      const minutes = Math.max(1, Math.ceil((result.data.seconds_left ?? 0) / 60));
      toast.push(
        "info",
        `Проверка «${account.name}» была недавно — следующая через ~${minutes} мин (защита IP)`,
      );
      return;
    }
    toast.push("info", `Проверка «${account.name}» идёт — обычно 30–60 секунд`);
    const before = account.last_check_at;
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      const freshItems = await fetchAccounts();
      setItems(freshItems);
      const current = freshItems.find((item) => item.id === account.id);
      if (current && current.last_check_at !== before) {
        setBusy(null);
        if (current.last_check_ok) {
          toast.push("success", `«${current.name}»: доступ есть`);
        } else {
          toast.push(
            "error",
            `«${current.name}»: проверка не прошла — ${current.last_error ?? "ошибка"}`,
          );
        }
        router.refresh();
        return;
      }
    }
    setBusy(null);
    toast.push("info", `Проверка «${account.name}» ещё выполняется — результат появится позже`);
    await refresh();
  }

  async function toggle(account: Account) {
    setBusy(account.id);
    const result = await updateAccountClient(account.id, {
      status: account.status === "active" ? "paused" : "active",
    });
    setBusy(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    toast.push(
      "info",
      account.status === "active" ? `«${account.name}» на паузе` : `«${account.name}» включён`,
    );
    await refresh();
  }

  async function switchRole(account: Account) {
    setBusy(account.id);
    const result = await updateAccountClient(account.id, {
      role: account.role === "seller" ? "searcher" : "seller",
    });
    setBusy(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    toast.push(
      "success",
      `«${account.name}»: роль → ${account.role === "seller" ? "поисковик" : "продавец"}`,
    );
    await refresh();
  }

  async function remove(account: Account) {
    const ok = await confirm({
      title: "Удалить аккаунт?",
      text: `«${account.name}» будет удалён, поиски перейдут на основной профиль. Каталог профиля останется на диске.`,
      confirmLabel: "Удалить",
      danger: true,
    });
    if (!ok) {
      return;
    }
    setBusy(account.id);
    const result = await deleteAccountClient(account.id);
    setBusy(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    toast.push("success", `Аккаунт «${account.name}» удалён`);
    await refresh();
  }

  async function saveProxy(account: Account) {
    setBusy(account.id);
    const result = await updateAccountClient(account.id, {
      proxy_label: proxyChoice || null,
    });
    setBusy(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    setProxyFor(null);
    toast.push("success", `«${account.name}»: прокси → ${proxyChoice || "личный IP"}`);
    await refresh();
  }

  async function submitCookies(account: Account) {
    if (!cookieText.trim()) {
      toast.push("error", "Вставьте cookies (JSON Cookie-Editor или строку Cookie)");
      return;
    }
    setBusy(account.id);
    const result = await uploadAccountCookiesClient(account.id, cookieText, fresh);
    setBusy(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    setCookieFor(null);
    setCookieText("");
    toast.push(
      "info",
      `Cookies для «${account.name}» загружаются в фоне; проверка появится в статусе`,
    );
    setTimeout(refresh, 6000);
  }

  const btn =
    "rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50";
  const input =
    "rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60";

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center">
          <h2 className="text-lg font-medium">Аккаунты</h2>
          <InfoHint
            title="Аккаунты и cookies"
            text="Каждый аккаунт — отдельный профиль Chromium со своими cookies. Роль «поисковик» — для обхода выдачи, «продавец» — для управления своими объявлениями. Поиск можно привязать только к «поисковику». Прокси можно закрепить за аккаунтом (sticky): cookies и выходной IP остаются одной связкой. Важно: Авито режет датацентр-прокси (403 «проблема с IP») даже с прогретыми cookies — личный IP или резидентные/мобильные прокси."
          />
        </div>
        <button
          type="button"
          onClick={() => setAddOpen(true)}
          className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 transition hover:bg-sky-500/20"
        >
          + Добавить аккаунт
        </button>
      </div>

      <details className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4 text-sm text-neutral-400">
        <summary className="cursor-pointer text-neutral-300">
          Мини-гайд: как залить аккаунт по cookies
        </summary>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-xs leading-relaxed">
          <li>
            Войдите в нужный аккаунт Авито в своём браузере (Brave/Chrome) — выдача должна
            открываться.
          </li>
          <li>
            Вариант А (быстро, из браузера на машине с Авито):
            <pre className="mt-1 overflow-x-auto rounded bg-neutral-950 p-2 font-mono text-[11px]">
{`make account-add name="Продавец 2"
make account-cookies name="Продавец 2" BROWSER=brave`}
            </pre>
          </li>
          <li>
            Вариант Б (через UI): нажмите «Cookies» у аккаунта и вставьте JSON из расширения
            Cookie-Editor (Export → JSON) или строку Cookie из DevTools. Кнопка «Загрузить»
            пишет cookies в профиль и проверяет выдачу.
          </li>
          <li>
            Проверьте кнопкой «Проверить»: статус должен стать «ок» (или покажет текст
            ошибки — например, 429/403 от Авито на датацентр-IP).
          </li>
          <li>
            Для сервера закрепите рабочий прокси: кнопка «Прокси» → выбрать из пула.
            Один профиль одновременно обходит один поиск (автозамок).
          </li>
        </ol>
      </details>

      <ul className="flex flex-col gap-3">
        {items.map((account) => (
          <li
            key={account.id}
            className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${
                      account.status !== "active"
                        ? "bg-neutral-500"
                        : account.last_check_ok === false
                          ? "bg-red-500"
                          : account.last_check_ok === true
                            ? "bg-emerald-400"
                            : "bg-amber-400"
                    }`}
                  />
                  <p className="font-medium">{account.name}</p>
                  {account.is_default ? (
                    <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-200">
                      основной
                    </span>
                  ) : null}
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] ${
                      account.role === "seller"
                        ? "border-violet-500/30 bg-violet-500/10 text-violet-200"
                        : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                    }`}
                  >
                    {account.role === "seller" ? "продавец" : "поисковик"}
                  </span>
                  {account.status !== "active" ? (
                    <span className="rounded-full border border-neutral-700 bg-neutral-800 px-2 py-0.5 text-[10px] text-neutral-400">
                      на паузе
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 font-mono text-[11px] text-neutral-500">
                  {account.profile_dir}
                  {!account.profile_exists ? " · профиль ещё не создан" : ""}
                </p>
                {!account.profile_exists ? (
                  <p className="mt-1 text-[11px] text-amber-300/80">
                    Профиля на сервере нет: залейте cookies кнопкой «Cookies» или
                    скопируйте каталог профиля с машины, где Авито уже работает.
                  </p>
                ) : null}
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
                  <span>поисков: {account.searches_count}</span>
                  <span
                    className={
                      account.proxy_label ? "text-amber-300/80" : "text-emerald-300/80"
                    }
                  >
                    прокси: {account.proxy_label ?? "личный IP"}
                  </span>
                  <span>
                    cookies:{" "}
                    {account.cookies_at ? formatRelativeTime(account.cookies_at) : "не залиты"}
                  </span>
                  <span>
                    проверка:{" "}
                    {account.last_check_at
                      ? account.last_check_ok
                        ? `ок, ${formatRelativeTime(account.last_check_at)}`
                        : `ошибка, ${formatRelativeTime(account.last_check_at)}`
                      : "не было"}
                  </span>
                  {account.last_error ? (
                    <span
                      className="max-w-[320px] truncate text-red-400/80"
                      title={account.last_error}
                    >
                      {account.last_error}
                    </span>
                  ) : null}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => check(account)}
                  disabled={busy === account.id}
                  className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1 text-xs text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-50"
                >
                  {busy === account.id ? "Проверка…" : "Проверить"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCookieFor(account);
                    setCookieText("");
                  }}
                  className={btn}
                >
                  Cookies
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setProxyFor(account);
                    setProxyChoice(account.proxy_label ?? "");
                  }}
                  className={btn}
                >
                  Прокси
                </button>
                <button
                  type="button"
                  onClick={() => toggle(account)}
                  disabled={busy === account.id}
                  className={btn}
                >
                  {account.status === "active" ? "Пауза" : "Включить"}
                </button>
                <button
                  type="button"
                  onClick={() => switchRole(account)}
                  disabled={busy === account.id}
                  className={btn}
                >
                  {account.role === "seller" ? "Сделать поисковиком" : "Сделать продавцом"}
                </button>
                {!account.is_default ? (
                  <button
                    type="button"
                    onClick={() => remove(account)}
                    disabled={busy === account.id}
                    className="rounded-lg border border-red-500/30 px-3 py-1 text-xs text-red-300 transition hover:border-red-500/60 disabled:opacity-50"
                  >
                    Удалить
                  </button>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Новый аккаунт"
        subtitle="Профиль Chromium со своими cookies"
        maxWidth="max-w-xl"
        footer={
          <>
            <button type="button" onClick={() => setAddOpen(false)} className={btn}>
              Отмена
            </button>
            <button
              type="button"
              onClick={add}
              disabled={busy === "add"}
              className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
            >
              {busy === "add" ? "Создание…" : "Создать"}
            </button>
          </>
        }
      >
        <div className="grid gap-3">
          <label className="flex flex-col gap-1 text-xs text-neutral-400">
            Название
            <input
              value={addName}
              onChange={(event) => setAddName(event.target.value)}
              placeholder="Например, Поисковик Армения"
              className={input}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-neutral-400">
            Роль
            <select
              value={addRole}
              onChange={(event) =>
                setAddRole(event.target.value === "seller" ? "seller" : "searcher")
              }
              className={input}
            >
              <option value="searcher">Поисковик (обход выдачи)</option>
              <option value="seller">Продавец (свои объявления)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-neutral-400">
            Прокси (можно закрепить позже)
            <select
              value={addProxy}
              onChange={(event) => setAddProxy(event.target.value)}
              className={input}
            >
              <option value="">личный IP (без прокси)</option>
              {proxyLabels.map((label) => (
                <option key={label} value={label}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-neutral-400">
            Заметка
            <input
              value={addNotes}
              onChange={(event) => setAddNotes(event.target.value)}
              placeholder="Необязательно"
              className={input}
            />
          </label>
        </div>
      </Modal>

      <Modal
        open={cookieFor !== null}
        onClose={() => setCookieFor(null)}
        title={`Cookies · ${cookieFor?.name ?? ""}`}
        subtitle="JSON из Cookie-Editor или строка Cookie из DevTools"
        maxWidth="max-w-2xl"
        footer={
          <>
            <button type="button" onClick={() => setCookieFor(null)} className={btn}>
              Отмена
            </button>
            <button
              type="button"
              onClick={() => cookieFor && submitCookies(cookieFor)}
              disabled={busy === cookieFor?.id}
              className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
            >
              {busy === cookieFor?.id ? "Загрузка…" : "Загрузить cookies"}
            </button>
          </>
        }
      >
        <textarea
          value={cookieText}
          onChange={(event) => setCookieText(event.target.value)}
          rows={10}
          placeholder='Вставьте JSON Cookie-Editor или строку "v=...; u=...; ft=..."'
          className="w-full rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-[11px] text-neutral-200 outline-none focus:border-sky-500/60"
        />
        <label className="mt-3 flex items-center gap-2 text-xs text-neutral-400">
          <input
            type="checkbox"
            checked={fresh}
            onChange={(event) => setFresh(event.target.checked)}
          />
          сбросить старый профиль (лечит «сожжённые» cookies)
        </label>
      </Modal>

      <Modal
        open={proxyFor !== null}
        onClose={() => setProxyFor(null)}
        title={`Прокси · ${proxyFor?.name ?? ""}`}
        subtitle="Sticky: один выходной IP для cookies этого аккаунта"
        maxWidth="max-w-xl"
        footer={
          <>
            <button type="button" onClick={() => setProxyFor(null)} className={btn}>
              Отмена
            </button>
            <button
              type="button"
              onClick={() => proxyFor && saveProxy(proxyFor)}
              disabled={busy === proxyFor?.id}
              className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
            >
              {busy === proxyFor?.id ? "Сохранение…" : "Сохранить прокси"}
            </button>
          </>
        }
      >
        <select
          value={proxyChoice}
          onChange={(event) => setProxyChoice(event.target.value)}
          className={`${input} w-full`}
        >
          <option value="">личный IP (без прокси)</option>
          {proxyLabels.map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
        </select>
        <p className="mt-3 text-xs text-neutral-500">
          Датацентр-прокси Авито обычно режет (403/429). Для обхода берите
          резидентные/мобильные и закрепляйте один за аккаунтом. Проверка аккаунта
          выполняется через тот же прокси.
        </p>
      </Modal>
    </section>
  );
}
