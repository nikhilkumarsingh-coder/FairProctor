import { useEffect } from "react";
import { CandidateShell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { closeCamera } from "@/lib/camera";
import { useT } from "@/lib/i18n";
import { navigate } from "@/lib/router";

export default function Done() {
  const { t } = useT();
  useEffect(() => closeCamera(), []);
  return (
    <CandidateShell>
      <div className="animate-fade-in space-y-6 pt-6 text-center">
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-300">
          <Icon name="checkCircle" size={44} />
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("doneTitle")}</h1>
          <p className="mx-auto mt-2 max-w-sm text-slate-600 dark:text-slate-300">{t("doneBody")}</p>
        </div>
        <div className="space-y-2">
          <Button size="lg" className="w-full" onClick={() => navigate("/exam/result")}>{t("seeResult")}<Icon name="arrowRight" size={18} /></Button>
          <Button variant="ghost" className="w-full" onClick={() => navigate("/exam")}>{t("backHome")}</Button>
        </div>
      </div>
    </CandidateShell>
  );
}
