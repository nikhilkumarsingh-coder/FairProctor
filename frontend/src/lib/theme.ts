import { store } from "./storage";

export function isDark() { return document.documentElement.classList.contains("dark"); }
export function setDark(dark: boolean) {
  document.documentElement.classList.toggle("dark", dark);
  store.set("fp-theme", dark ? "dark" : "light");
}
