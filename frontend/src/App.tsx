// The candidate app (served at /): log in with roll no. + login code, consent, pre-check, test, result.
// Reviewers and admins use the staff app (src/staff, served at /staff); there is no sign-up.
import { AppCore, CAND, type RouteDef } from "./AppCore";
import Account from "./pages/account/Account";
import Login from "./pages/auth/Login";
import Consent from "./pages/exam/Consent";
import Done from "./pages/exam/Done";
import Exam from "./pages/exam/Exam";
import Home from "./pages/exam/Home";
import Precheck from "./pages/exam/Precheck";
import Result from "./pages/exam/Result";

const routes: RouteDef[] = [
  { path: "/login", page: () => <Login /> },
  { path: "/account", roles: CAND, page: () => <Account /> },
  { path: "/exam", roles: CAND, page: () => <Home /> },
  { path: "/exam/consent", roles: CAND, page: () => <Consent /> },
  { path: "/exam/precheck", roles: CAND, page: () => <Precheck /> },
  { path: "/exam/run", roles: CAND, page: () => <Exam /> },
  { path: "/exam/done", roles: CAND, page: () => <Done /> },
  { path: "/exam/result", roles: CAND, page: () => <Result /> },
];

export default function App() {
  return <AppCore app="candidate" routes={routes} loginPath="/login" roots={["/"]}
    otherApp={{ href: "/staff/login", label: "Reviewers and admins: go to the staff login" }} />;
}
