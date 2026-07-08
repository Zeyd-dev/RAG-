import { useState } from "react";

/**
 * Renders The Dot's logo from /public/thedot-logo.png (Vite serves
 * anything in /public at the site root, so no import/build step is
 * needed -- just replace the file to change the logo). Falls back to a
 * simple text mark if that file is ever missing, so the header never
 * shows a broken-image icon.
 */
export default function Logo({ className = "h-8 w-auto" }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <span className={`inline-flex items-center gap-1.5 font-semibold text-slate-900 ${className}`}>
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-brand-500" />
        the dot
      </span>
    );
  }

  return (
    <img
      src="/thedot-logo.png"
      alt="The Dot"
      className={className}
      onError={() => setFailed(true)}
    />
  );
}
