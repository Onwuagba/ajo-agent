import type { ReactNode } from "react";
import { FlaskConical, LogOut, Moon, Sun } from "lucide-react";
import { Mark } from "./ui";
import { navigate, setTheme, signOut, useStore } from "../state/store";

/** Page frame for everything outside a running circle: sign-in, the circle list, creating a circle, invites and setup. */
export function Chrome({ children, narrow = false }: { children: ReactNode; narrow?: boolean }) {
  const auth = useStore((s) => s.auth); const theme = useStore((s) => s.theme); const sandbox = useStore((s) => s.sandbox);
  return (
    <div className="chrome">
      <header className="chrome-top">
        <button className="brand-btn" onClick={() => navigate(auth ? "#/groups" : "#/")} aria-label="Ajo home"><span className="brand-mark"><Mark size={22} /></span><span className="brand-name">Ajo</span></button>
        {sandbox && <span className="sandbox"><FlaskConical size={14} /> Sandbox · no real money</span>}
        <span className="grow" />
        <button className="btn sm" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">{theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}</button>
        {auth && <><span className="who-chip"><span className="avatar" style={{ "--h": 158, "--s": "28px" } as React.CSSProperties}>{auth.name.split(" ").map((p) => p[0]).slice(0, 2).join("")}</span><span className="who-name">{auth.name}</span></span><button className="btn sm" onClick={() => void signOut()}><LogOut size={15} /> Sign out</button></>}
      </header>
      <main className={`chrome-main ${narrow ? "narrow" : ""}`}>{children}</main>
    </div>
  );
}
