"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { InfoHint } from "@/app/components/info-hint";
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
  const [items, setItems] = useState(initial);
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [role, setRole] = useState<"searcher" | "seller">("searcher");
  const [cookieFor, setCookieFor] = useState<string | null>(null);
  const [cookieText, setCookieText] = useState("");
  const [fresh, setFresh] = useState(true);
  const [proxyFor, setProxyFor] = useState<string | null>(null);
  const [proxyChoice, setProxyChoice] = useState("");
  const [addProxy, setAddProxy] = useState("");
  const [proxyLabels, setProxyLabels] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    if (!name.trim()) {
      setError("Укажите название аккаунта");
      return;
    }
    setBusy("add");
    const result = await createAccountClient({
      name: name.trim(),
      notes: notes.trim() || null,
      role,
      proxy_label: addProxy || null,
    });
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setName("");
    setNotes("");
    setAddProxy("");
    setShowAdd(false);
    setMessage("Аккаунт создан — залейте cookies");
    await refresh();
  }

  async function check(account: Account) {
    setBusy(account.id);
    const result = await checkAccountClient(account.id);
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    if (result.data?.status === "cooldown") {
      const minutes = Math.max(1, Math.ceil((result.data.seconds_left ?? 0) / 60));
      setMessage(
        `Проверка «${account.name}» была недавно — следующая через ~${minutes} мин (защита IP)`,
      );
      return;
    }
    setMessage(`Проверка «${account.name}» в очереди — обновится через несколько секунд`);
    setTimeout(refresh, 4000);
  }

  async function toggle(account: Account) {
    setBusy(account.id);
    const result = await updateAccountClient(account.id, {
      status: account.status === "active" ? "paused" : "active",
    });
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    await refresh();
  }

  async function switchRole(account: Account) {
    setBusy(account.id);
    const result = await updateAccountClient(account.id, {
      role: account.role === "seller" ? "searcher" : "seller",
    });
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setMessage(
      `«${account.name}»: роль → ${account.role === "seller" ? "поисковик" : "продавец"}`,
    );
    await refresh();
  }

  async function remove(account: Account) {
    if (!window.confirm(`Удалить аккаунт «${account.name}»? Поиски перейдут на основной.`)) {
      return;
    }
    setBusy(account.id);
    const result = await deleteAccountClient(account.id);
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    await refresh();
  }

  async function saveProxy(account: Account) {
    setBusy(account.id);
    const result = await updateAccountClient(account.id, {
      proxy_label: proxyChoice || null,
    });
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setProxyFor(null);
    setMessage(
      `«${account.name}»: прокси → ${proxyChoice || "личный IP"}`,
    );
    await refresh();
  }

  async function submitCookies(account: Account) {
    if (!cookieText.trim()) {
      setError("Вставьте cookies (JSON Cookie-Editor или строку Cookie)");
      return;
    }
    setBusy(account.id);
    const result = await uploadAccountCookiesClient(account.id, cookieText, fresh);
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setCookieFor(null);
    setCookieText("");
    setMessage(
      `Cookies для «${account.name}» загружаются в фоне; проверка появится в статусе`,
    );
    setTimeout(refresh, 6000);
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center">
          <h2 className="text-lg font-medium">Аккаунты</h2>
          <InfoHint
            title="Аккаунты и cookies"
            text="Каждый аккаунт — отдельный профиль Chromium со своими cookies. Роль «поисковик» — для обхода выдачи, «продавец» — для управления своими объявлениями. Поиск можно привязать только к «поисковику». Прокси можно закрепить за аккаунтом (sticky): cookies и выходной IP остаются одной связкой. Важно: Авито режет датацентр-прокси (403 «проблема с IP») даже с прогретыми cookies — личный IP или резидентные/мобильные прокси. Cookies можно вставить сюда или залить из браузера командой make account-cookies."
          />
        </div>
        <button
          type="button"
          onClick={() => setShowAdd((value) => !value)}
          className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 transition hover:bg-sky-500/20"
        >
          + Добавить аккаунт
        </button>
      </div>

      {message ? <p className="text-xs text-emerald-300">{message}</p> : null}
      {error ? <p className="text-xs text-red-300">{error}</p> : null}

      {showAdd ? (
        <div className="rounded-xl border border-sky-500/25 bg-neutral-900/70 p-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Название (например, Продавец 2)"
              className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
            />
            <select
              value={role}
              onChange={(event) =>
                setRole(event.target.value === "seller" ? "seller" : "searcher")
              }
              className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
            >
              <option value="searcher">Поисковик (обход выдачи)</option>
              <option value="seller">Продавец (свои объявления)</option>
            </select>
            <input
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Заметка (необязательно)"
              className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
            />
            <select
              value={addProxy}
              onChange={(event) => setAddProxy(event.target.value)}
              className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60 sm:col-span-3"
            >
              <option value="">Прокси: личный IP (рекомендуется)</option>
              {proxyLabels.map((label) => (
                <option key={label} value={label}>
                  Прокси: {label}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={add}
            disabled={busy === "add"}
            className="mt-3 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {busy === "add" ? "Создание…" : "Создать"}
          </button>
        </div>
      ) : null}

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
            Вариант А (быстро, из браузера на этой машине):
            <pre className="mt-1 overflow-x-auto rounded bg-neutral-950 p-2 font-mono text-[11px]">
{`make account-add name="Продавец 2"
make account-cookies name="Продавец 2" BROWSER=brave`}
            </pre>
          </li>
          <li>
            Вариант Б (через UI): нажмите «Cookies» у аккаунта и вставьте JSON из расширения
            Cookie-Editor (Export → JSON) или строку Cookie из DevTools. Кнопка «Загрузить»
            пишет cookies в профиль и проверяет выдачу.
            {" "}Сервер без графики: используйте CLI на машине с браузером и скопируйте
            каталог <code>.accounts/&lt;slug&gt;</code> на сервер.
          </li>
          <li>
            Проверьте кнопкой «Проверить»: статус должен стать «Проверен», объявлений &gt; 0.
          </li>
          <li>
            Привяжите аккаунт к поиску: «Изменить» у поиска → поле «Аккаунт». Один профиль
            одновременно обходит только один поиск (стоит автозамок).
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
                    <span className="max-w-[280px] truncate text-red-400/80">
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
                  Проверить
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCookieFor(cookieFor === account.id ? null : account.id);
                    setError(null);
                  }}
                  className="rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500"
                >
                  Cookies
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setProxyFor(proxyFor === account.id ? null : account.id);
                    setProxyChoice(account.proxy_label ?? "");
                    setError(null);
                  }}
                  className="rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500"
                >
                  Прокси
                </button>
                <button
                  type="button"
                  onClick={() => toggle(account)}
                  disabled={busy === account.id}
                  className="rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50"
                >
                  {account.status === "active" ? "Пауза" : "Включить"}
                </button>
                <button
                  type="button"
                  onClick={() => switchRole(account)}
                  disabled={busy === account.id}
                  className="rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50"
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

            {proxyFor === account.id ? (
              <div className="mt-3 rounded-lg border border-neutral-800 bg-neutral-950/60 p-3">
                <p className="mb-2 text-xs text-neutral-400">
                  Sticky-прокси: один выходной IP для cookies этого аккаунта. Датацентр
                  Авито обычно режет (403), берите резидентные/мобильные.
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <select
                    value={proxyChoice}
                    onChange={(event) => setProxyChoice(event.target.value)}
                    className="min-w-[260px] rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs text-neutral-200 outline-none focus:border-sky-500/60"
                  >
                    <option value="">личный IP (без прокси)</option>
                    {proxyLabels.map((label) => (
                      <option key={label} value={label}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => saveProxy(account)}
                    disabled={busy === account.id}
                    className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    {busy === account.id ? "Сохранение…" : "Сохранить прокси"}
                  </button>
                </div>
              </div>
            ) : null}

            {cookieFor === account.id ? (
              <div className="mt-3 rounded-lg border border-neutral-800 bg-neutral-950/60 p-3">
                <textarea
                  value={cookieText}
                  onChange={(event) => setCookieText(event.target.value)}
                  rows={4}
                  placeholder='Вставьте JSON Cookie-Editor или строку "v=...; u=...; ft=..."'
                  className="w-full rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-[11px] text-neutral-200 outline-none focus:border-sky-500/60"
                />
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2 text-xs text-neutral-400">
                    <input
                      type="checkbox"
                      checked={fresh}
                      onChange={(event) => setFresh(event.target.checked)}
                    />
                    сбросить старый профиль (лечит «сожжённые» cookies)
                  </label>
                  <button
                    type="button"
                    onClick={() => submitCookies(account)}
                    disabled={busy === account.id}
                    className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    {busy === account.id ? "Загрузка…" : "Загрузить cookies"}
                  </button>
                </div>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
