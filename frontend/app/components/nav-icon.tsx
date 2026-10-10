type IconName =
  | "overview"
  | "searches"
  | "listings"
  | "recommendations"
  | "agents"
  | "chat"
  | "accounts"
  | "proxies"
  | "alerts";

const paths: Record<IconName, string> = {
  overview: "M3 13h8V3H3v10Zm10 8h8V11h-8v10ZM3 21h8v-6H3v6Zm10-18v6h8V3h-8Z",
  searches: "m4 4 7.5 7.5m0 0L20 3m-8.5 8.5L20 20M4 20l5-5",
  listings: "M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v13a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 18.5v-13Z M8 7h8M8 11h8M8 15h5",
  recommendations: "m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2-4.5-4.4 6.2-.9L12 3Z",
  agents: "M12 3v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.8 2.8m6.4 6.4 2.8 2.8m0-12-2.8 2.8m-6.4 6.4-2.8 2.8 M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z",
  chat: "M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 4v-4.2A2.5 2.5 0 0 1 4 13.5v-8Z",
  accounts: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 9a7 7 0 0 1 14 0",
  proxies: "M4 7h16M4 12h16M4 17h16M8 7v.01M16 12v.01M10 17v.01",
  alerts: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Zm-8 13h4",
};

export function Icon({ name, decorative = true }: { name: IconName; decorative?: boolean }) {
  return (
    <svg
      aria-hidden={decorative}
      className="h-4 w-4 shrink-0"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name]} />
    </svg>
  );
}
