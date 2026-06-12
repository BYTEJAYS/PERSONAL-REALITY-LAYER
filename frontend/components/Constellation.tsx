"use client";

/* The constellation switcher — doors to the sister rooms.
   Shared design language: deep ink + brass gold. Local-first defaults;
   override with NEXT_PUBLIC_*_URL for deployed builds. */

const ROOMS = [
  {
    name: "Hall",
    glyph: "✦",
    href: process.env.NEXT_PUBLIC_HUB_URL ?? "http://localhost:3333",
    title: "The Constellation — entrance hall",
  },
  {
    name: "Ascension",
    glyph: "🜂",
    href: process.env.NEXT_PUBLIC_ASCENSION_URL ?? "http://localhost:3000",
    title: "ASCENSION — the action layer",
  },
  {
    name: "Legacy",
    glyph: "◈",
    href: process.env.NEXT_PUBLIC_LEGACY_URL ?? "http://localhost:3088",
    title: "LEGACY — the meaning layer",
  },
];

export function Constellation() {
  return (
    <nav className="fixed bottom-4 right-4 z-30 flex items-center gap-1 rounded-2xl border border-[#b08d57]/25 bg-black/60 px-2 py-1.5 backdrop-blur-md">
      {ROOMS.map((room) => (
        <a
          key={room.name}
          href={room.href}
          title={room.title}
          className="group flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-400 transition-colors hover:bg-white/[0.06] hover:text-[#c9a36a]"
        >
          <span className="text-[12px] leading-none text-[#b08d57] opacity-80 group-hover:opacity-100">
            {room.glyph}
          </span>
          <span className="hidden sm:inline">{room.name}</span>
        </a>
      ))}
    </nav>
  );
}
