export default function SearchLoading() {
  return (
    <main className="mx-auto flex max-w-6xl animate-pulse flex-col gap-6 px-4 py-8 sm:gap-8 sm:px-6 sm:py-12">
      <div className="flex flex-col gap-3">
        <div className="h-3 w-28 rounded bg-neutral-800" />
        <div className="h-7 w-2/3 max-w-md rounded bg-neutral-800" />
        <div className="h-3 w-full max-w-lg rounded bg-neutral-800/70" />
      </div>
      <div className="h-24 rounded-xl border border-neutral-800 bg-neutral-900/60" />
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, index) => (
          <div
            key={index}
            className="h-20 rounded-xl border border-neutral-800 bg-neutral-900/60"
          />
        ))}
      </div>
      <div className="h-72 rounded-xl border border-neutral-800 bg-neutral-900/60" />
      <div className="flex flex-col gap-3">
        <div className="h-5 w-40 rounded bg-neutral-800" />
        {Array.from({ length: 6 }).map((_, index) => (
          <div
            key={index}
            className="h-14 rounded-lg border border-neutral-800 bg-neutral-900/40"
          />
        ))}
      </div>
    </main>
  );
}
