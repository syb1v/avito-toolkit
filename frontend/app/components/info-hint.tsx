export function InfoHint({
  title,
  text,
  lines,
}: {
  title?: string;
  text?: string;
  lines?: { label: string; value: string }[];
}) {
  return (
    <span className="group relative inline-flex align-middle">
      <span
        tabIndex={0}
        role="button"
        aria-label={title ? `Пояснение: ${title}` : "Пояснение"}
        className="ml-1.5 flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-neutral-600 text-[10px] leading-none text-neutral-400 transition hover:border-neutral-400 hover:text-neutral-200 focus:outline-none focus:ring-1 focus:ring-neutral-500"
      >
        ?
      </span>
      <span className="pointer-events-none absolute left-1/2 top-full z-30 mt-2 hidden w-64 -translate-x-1/2 rounded-lg border border-neutral-700 bg-neutral-900 p-3 text-left text-xs font-normal normal-case tracking-normal text-neutral-300 shadow-xl group-hover:block group-focus-within:block sm:w-72">
        {title ? (
          <span className="mb-1 block font-medium text-neutral-100">{title}</span>
        ) : null}
        {text}
        {lines ? (
          <span className="mt-1.5 flex flex-col gap-1">
            {lines.map((line) => (
              <span key={line.label}>
                <b className="text-neutral-100">{line.label}</b> — {line.value}
              </span>
            ))}
          </span>
        ) : null}
      </span>
    </span>
  );
}
