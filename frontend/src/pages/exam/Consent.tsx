import { useState } from "react";
import { CandidateShell, ErrorBox, Loading } from "@/components/Shell";
import { Icon, type IconName } from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";
import { api, ApiError } from "@/lib/api";
import { errorFor } from "@/lib/errors";
import { useT, type Key } from "@/lib/i18n";
import { navigate } from "@/lib/router";
import { store } from "@/lib/storage";
import type { ExamMe } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function Section({ icon, tone, title, items }: { icon: IconName; tone: string; title: string; items: string[] }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <span className={`grid h-8 w-8 place-items-center rounded-full ${tone}`}><Icon name={icon} size={16} /></span>{title}
        </h2>
        <ul className="mt-3 space-y-2">
          {items.map((it, i) => <li key={i} className="flex gap-2 leading-snug"><span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />{it}</li>)}
        </ul>
      </CardContent>
    </Card>
  );
}

export default function Consent() {
  const { t } = useT();
  const { data, error, loading, slow, reload } = useApi<ExamMe>("/api/exam/me");
  const [understood, setUnderstood] = useState(false);
  const [share, setShare] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function go() {
    if (!data) return;
    if (!understood) { setErr(t("understood") + " ✓"); return; }
    setBusy(true); setErr(null);
    try {
      await api("/api/exam/consent", { body: { version: data.consent.version_needed, understood, camera_ok: true, precheck_share_ok: share } });
      store.set("fp-camera", "yes");
      navigate("/exam/precheck");
    } catch (e) {
      if (e instanceof ApiError && e.code === "old_consent") reload();
      setErr(errorFor(e, t));
    } finally { setBusy(false); }
  }
  const k = (...keys: Key[]) => keys.map((x) => t(x, { days: data?.retention_days ?? 90 }));

  return (
    <CandidateShell>
      {loading && !data ? <Loading slow={slow} /> : error ? <ErrorBox error={error} retry={reload} /> : (
        <div className="animate-fade-in space-y-4">
          <h1 className="text-2xl font-semibold tracking-tight">{t("consentTitle")}</h1>
          <Section icon="eye" tone="bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300" title={t("recordedTitle")} items={k("recorded1", "recorded2", "recorded3", "recorded4", "recorded5", "recorded6")} />
          <Section icon="lock" tone="bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" title={t("neverTitle")} items={k("never1", "never2", "never3", "never4")} />
          <Section icon="scale" tone="bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300" title={t("rightsTitle")} items={k("rights1", "rights2", "rights3", "rights4")} />
          <Alert tone="success" className="flex gap-2 text-base"><Icon name="users" size={20} className="mt-0.5 shrink-0" />{t("fairLine")}</Alert>
          <Card>
            <CardContent className="space-y-4 pt-5">
              <Alert tone="info" className="flex gap-2"><Icon name="camera" size={18} className="mt-0.5 shrink-0" />{t("cameraRequired")}</Alert>
              <Checkbox id="understood" checked={understood} onChange={(v) => { setUnderstood(v); setErr(null); }}><b>{t("understood")}</b></Checkbox>
              <Checkbox id="share" checked={share} onChange={setShare}><span className="text-slate-600 dark:text-slate-300">{t("shareNumbers")}</span></Checkbox>
            </CardContent>
          </Card>
          {err && <Alert>{err}</Alert>}
          <div className="sticky bottom-0 -mx-4 bg-gradient-to-t from-slate-100 via-slate-100/95 to-transparent px-4 pt-6 pb-4 dark:from-slate-950 dark:via-slate-950/95">
            <Button size="lg" className="w-full" disabled={busy || !understood} onClick={go}>{busy ? t("loading") : t("continue")} <Icon name="arrowRight" size={18} /></Button>
          </div>
        </div>
      )}
    </CandidateShell>
  );
}
