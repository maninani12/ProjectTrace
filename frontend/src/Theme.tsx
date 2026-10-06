import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

type Mode = "light" | "dark" | "system";
const ThemeContext = createContext({
  mode: "system" as Mode,
  resolved: "light",
  setMode: (_: Mode) => {},
});
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>("system");
  const [systemDark, setSystemDark] = useState(false);
  useEffect(() => {
    const saved = localStorage.getItem("pt-theme");
    if (saved === "light" || saved === "dark" || saved === "system")
      setMode(saved);
    if (!window.matchMedia) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(media.matches);
    const update = () => setSystemDark(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  const resolved = mode === "system" ? (systemDark ? "dark" : "light") : mode;
  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
  }, [resolved]);
  function change(value: Mode) {
    setMode(value);
    localStorage.setItem("pt-theme", value);
  }
  return (
    <ThemeContext.Provider value={{ mode, resolved, setMode: change }}>
      {children}
    </ThemeContext.Provider>
  );
}
export const useTheme = () => useContext(ThemeContext);
export function ThemeControl() {
  const { mode, setMode } = useTheme();
  return (
    <label className="theme-control">
      Appearance{" "}
      <select
        aria-label="Appearance"
        value={mode}
        onChange={(e) => setMode(e.target.value as Mode)}
      >
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}
