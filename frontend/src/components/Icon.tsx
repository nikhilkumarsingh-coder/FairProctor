// A small stroke icon set (24×24, lucide-style), so no icon package is needed.
import type { SVGProps } from "react";

const P: Record<string, string> = {
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18M6 6l12 12",
  alert: "M12 3 2 20h20L12 3zM12 10v4M12 17.5v.01",
  shield: "M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6l-8-3zM9 12l2 2 4-4",
  camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  cameraOff: "M3 3l18 18M8 5h7l2 3h3v10M4 8v11h13M12 9a4 4 0 0 1 4 4",
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3M9 21h6",
  micOff: "M3 3l18 18M9 9v3a3 3 0 0 0 5.1 2.1M15 9.3V6a3 3 0 0 0-5.7-1.3M5 11a7 7 0 0 0 11.5 5.4M19 11a7 7 0 0 1-.6 2.8M12 18v3M9 21h6",
  wifi: "M2 9a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 19.5v.01",
  wifiOff: "M3 3l18 18M8.5 16a5 5 0 0 1 7 0M5 12.5a10 10 0 0 1 5-2.6M2 9a15 15 0 0 1 4.5-3M14 10a10 10 0 0 1 5 2.5M17.5 6A15 15 0 0 1 22 9M12 19.5v.01",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  left: "M15 18l-6-6 6-6",
  right: "M9 18l6-6-6-6",
  grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z",
  logout: "M9 21H5V3h4M16 17l5-5-5-5M21 12H9",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  users: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M16 3.5a4 4 0 0 1 0 7.5M22 21a7 7 0 0 0-4-6.3",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
  upload: "M12 15V3M7 8l5-5 5 5M4 15v6h16v-6",
  download: "M12 3v12M7 10l5 5 5-5M4 15v6h16v-6",
  file: "M14 3H6v18h12V7zM14 3v4h4M9 13h6M9 17h6",
  play: "M7 4l13 8-13 8z",
  flag: "M5 21V4M5 4h11l-2 4 2 4H5",
  timer: "M10 2h4M12 14l3-3M12 22a8 8 0 1 0 0-16 8 8 0 0 0 0 16z",
  pause: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM10 9v6M14 9v6",
  window: "M3 5h18v14H3zM3 9h18M15 14l3 3m0-3-3 3",
  paste: "M9 4h6v3H9zM8 5H5v16h14V5h-3M9 12h6M9 16h4",
  userPlus: "M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M19 8v6M16 11h6",
  match: "M8 7a4 4 0 1 0 0 8M16 7a4 4 0 1 1 0 8M8 11h8",
  lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
  mail: "M3 5h18v14H3zM3 6l9 7 9-7",
  key: "M15 7a4 4 0 1 1-3.9 5H3v3h3v3h3v-3h2.1",
  sparkles: "M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.5v.01",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4z",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  languages: "M4 5h9M8.5 3v2M6 5c.5 3 2.5 6 6 8M11 5c-.5 3-3 7-7 9M13 21l4-10 4 10M14.5 17.5h5",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  arrowRight: "M5 12h14M13 6l6 6-6 6",
  bookmark: "M6 3h12v18l-6-4-6 4z",
  checkCircle: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6",
  phone: "M8 2h8a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1zM11 18h2",
  monitor: "M3 4h18v12H3zM8 20h8M12 16v4",
  gauge: "M12 21a9 9 0 1 1 9-9M12 12l5-4",
  sunDim: "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 4v.01M12 20v.01M4 12h.01M20 12h.01M6.3 6.3h.01M17.7 17.7h.01M6.3 17.7h.01M17.7 6.3h.01",
  scan: "M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  aperture: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  scale: "M12 3v18M5 21h14M6 7h12M6 7l-3 7h6zM18 7l-3 7h6z",
  inbox: "M3 13h5l2 3h4l2-3h5M3 13l3-8h12l3 8v7H3z",
  code: "M8 6l-6 6 6 6M16 6l6 6-6 6M14 4l-4 16",
  terminal: "M4 17l6-5-6-5M12 19h8",
  calculator: "M6 2h12a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM8 6h8v4H8zM8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01M16 18h.01",
};

export type IconName = keyof typeof P;

export function Icon({ name, size = 20, className, title, ...rest }: { name: IconName; size?: number; title?: string } & SVGProps<SVGSVGElement>) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round"
      strokeLinejoin="round" className={className} aria-hidden={title ? undefined : true} role={title ? "img" : undefined} {...rest}>
      {title && <title>{title}</title>}
      <path d={P[name]} />
    </svg>
  );
}
