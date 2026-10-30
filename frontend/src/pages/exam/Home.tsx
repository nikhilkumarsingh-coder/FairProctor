import { CandidateShell, ErrorBox, Loading } from "@/components/Shell";
import { Icon, type IconName } from "@/components/Icon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/misc";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { dateTime } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { navigate } from "@/lib/router";
import { sebLink } from "@/lib/seb";
import type { ExamMe } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function Home() {
  const { t } = useT();
  const { user } = useAuth();
  const { data, error, loading, slow, reload } = useApi<ExamMe>("/api/exam/me");
  return (
    <CandidateShell>
      <div className="animate-fade-in space-y-5">
        <div>
          <p className="text-sm font-semibold text-pink-700 dark:text-pink-400">{t("welcome")}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{t("hello", { name: user?.name || "" })}</h1>
        </div>
        {loading && !data ? <Loading slow={slow} /> : error ? <ErrorBox error={error} retry={reload} /> : data && (
          data.join_needed ? <NotInTest /> : <TestCard me={data} />
        )}
      </div>
    </CandidateShell>
  );
}

/** No test yet: candidates do not join with a code any more; the test centre adds them to a sitting. */
function NotInTest() {
  const { t } = useT();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("noTestTitle")}</CardTitle>
        <CardDescription>{t("noTestHelp")}</CardDescription>
      </CardHeader>
    </Card>
  );
}

function TestCard({ me }: { me: ExamMe }) {
  const { t, lang } = useT();
  const s = me.session!, sit = me.sitting!, test = me.test!;
  const status = s.status;
  const steps: { icon: IconName; label: string; done: boolean }[] = [
    { icon: "shield", label: t("stepConsent"), done: me.consent.given },
    { icon: "camera", label: t("stepPrecheck"), done: status !== "not_started" },
    { icon: "play", label: t("stepStart"), done: status !== "not_started" },
  ];
  const next = () => navigate(status === "in_progress" ? "/exam/run" : me.consent.given ? "/exam/precheck" : "/exam/consent");
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-slate-200 border-l-4 border-l-pink-600 bg-slate-50 px-5 py-4 dark:border-slate-800 dark:border-l-pink-400 dark:bg-slate-900">
        <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{sit.title}</p>
        <h2 className="mt-1 text-xl font-semibold leading-snug text-slate-900 dark:text-slate-50">{test.title}</h2>
        <div className="mt-3 flex flex-wrap gap-2 text-sm">
          {test.kind === "coding" && <span className="inline-flex items-center gap-1 rounded-md border border-pink-200 bg-pink-50 px-2 py-0.5 font-medium text-pink-800 dark:border-pink-900 dark:bg-pink-950 dark:text-pink-200"><Icon name="code" size={14} />{t("codingTest")}</span>}
          <span className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"><Icon name="clock" size={14} />{t("minutes", { n: test.duration_min })}</span>
          <span className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"><Icon name="file" size={14} />{test.kind === "coding" ? `${test.n_items} ${t("problemsLabel").toLowerCase()}` : t("questions", { n: test.n_items })}</span>
        </div>
      </div>
      <CardContent className="space-y-5 pt-5">
        {status === "submitted" ? (
          <>
            <Alert tone="success" className="flex items-center gap-2"><Icon name="checkCircle" size={18} />{t("submittedCard")}</Alert>
            <p className="text-slate-600 dark:text-slate-300">{me.result_ready ? "" : t("resultSoon")}</p>
            <Button size="lg" className="w-full" onClick={() => navigate("/exam/result")}>{t("seeResult")} <Icon name="arrowRight" size={18} /></Button>
          </>
        ) : sit.status === "scheduled" ? (
          <Alert tone="info">{t("startsIn", { time: dateTime(sit.starts_at, lang) })}</Alert>
        ) : !me.can_start ? (
          <Alert tone="warning">{t("closed")}</Alert>
        ) : me.seb?.required && !me.seb.verified ? (
          <SebGate seb={me.seb} />
        ) : (
          <>
            {me.seb?.required && <Alert tone="success" className="flex items-center gap-2"><Icon name="lock" size={16} />{t("sebVerified")}</Alert>}
            {s.reopened && status === "in_progress" && <Alert tone="success"><b>{t("reopenedTitle")}.</b> {t("reopenedBody")}</Alert>}
            {status === "not_started" && (
              <ol className="space-y-2">
                {steps.map((st, i) => (
                  <li key={i} className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950">
                    <span className={cn("grid h-9 w-9 place-items-center rounded-full", st.done ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" : "bg-slate-100 text-slate-500 dark:bg-slate-800")}>
                      <Icon name={st.done ? "check" : st.icon} size={18} />
                    </span>
                    <span className="flex-1 font-medium">{st.label}</span>
                    {st.done && <Badge tone="success">{t("stepDoneLabel")}</Badge>}
                  </li>
                ))}
              </ol>
            )}
            <Button size="lg" className="w-full" onClick={next}>
              {status === "in_progress" ? t("resume") : t("continue")} <Icon name="arrowRight" size={18} />
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** The sitting requires Safe Exam Browser and this page is not running in it (or not with the right settings). */
function SebGate({ seb }: { seb: NonNullable<ExamMe["seb"]> }) {
  const { t } = useT();
  return (
    <div className="space-y-4">
      <Alert tone="warning" className="space-y-1">
        <p className="flex items-center gap-2 font-semibold"><Icon name="lock" size={16} />{t("sebTitle")}</p>
        <p className="text-sm">{seb.in_seb ? t("sebWrongSettings") : t("sebBody")}</p>
      </Alert>
      <ol className="list-decimal space-y-2 pl-5 text-sm text-slate-700 dark:text-slate-300">
        <li>{t("sebStep1")} <a href={seb.download_url} target="_blank" rel="noreferrer" className="font-semibold text-pink-700 underline dark:text-pink-400">safeexambrowser.org</a></li>
        <li>{t("sebStep2")}</li>
        <li>{t("sebStep3")}</li>
      </ol>
      {seb.config_url ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <a href={sebLink(seb.config_url)} className="inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-brand px-5 font-medium text-white hover:bg-brand-hover dark:text-slate-950">
            <Icon name="lock" size={18} />{t("sebOpen")}
          </a>
          <a href={seb.config_url} download className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-5 font-medium hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900">
            <Icon name="download" size={18} />{t("sebDownload")}
          </a>
        </div>
      ) : <p className="text-sm text-slate-500">{t("sebAskCentre")}</p>}
      <p className="text-xs text-slate-500">{t("sebPhones")}</p>
    </div>
  );
}
