// The staff app (served at /staff, /admin, /review): reviewers and admins log in with email + password.
// Admin accounts are made with `python -m backend.scripts.create_admin`; admins add reviewers and candidates here.
import { AppCore, ADMIN, REV, type RouteDef } from "../AppCore";
import Account from "../pages/account/Account";
import AdminHome from "../pages/admin/AdminHome";
import FairnessPage from "../pages/admin/Fairness";
import SittingPage from "../pages/admin/SittingPage";
import TestPage from "../pages/admin/TestPage";
import StaffLogin from "../pages/auth/StaffLogin";
import Appeals from "../pages/review/Appeals";
import Exams from "../pages/review/Exams";
import { LiveList, LiveMonitor } from "../pages/review/Live";
import Queue from "../pages/review/Queue";
import Session from "../pages/review/Session";

const routes: RouteDef[] = [
  { path: "/staff/login", page: () => <StaffLogin /> },
  { path: "/staff/account", roles: REV, page: () => <Account /> },
  { path: "/review", roles: REV, page: () => <Queue /> },
  { path: "/review/s/:id", roles: REV, page: (p) => <Session id={p.id} /> },
  { path: "/review/exams", roles: REV, page: () => <Exams /> },
  { path: "/review/appeals", roles: REV, page: () => <Appeals /> },
  { path: "/review/live", roles: REV, page: () => <LiveList /> },
  { path: "/review/live/:id", roles: REV, page: (p) => <LiveMonitor id={Number(p.id)} /> },
  { path: "/admin", roles: ADMIN, page: () => <AdminHome /> },
  { path: "/admin/tests/:id", roles: ADMIN, page: (p) => <TestPage id={Number(p.id)} /> },
  { path: "/admin/sittings/:id", roles: ADMIN, page: (p) => <SittingPage id={Number(p.id)} /> },
  { path: "/admin/sittings/:id/fairness", roles: ADMIN, page: (p) => <FairnessPage id={Number(p.id)} /> },
];

export default function StaffApp() {
  return <AppCore app="staff" routes={routes} loginPath="/staff/login" roots={["/staff", "/staff/"]}
    otherApp={{ href: "/", label: "Candidates: go to the test login" }} />;
}
