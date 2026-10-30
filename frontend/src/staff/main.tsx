import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { setTokenKey } from "../lib/api";
import "../styles.css";
import StaffApp from "./App";

setTokenKey("fp-staff-token");           // its own login, separate from the candidate pages on the same address

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StaffApp />
  </StrictMode>,
);
