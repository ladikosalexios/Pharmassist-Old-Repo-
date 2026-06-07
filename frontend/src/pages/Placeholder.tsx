import { useTranslation } from "react-i18next";

export function Placeholder({ title }: { title: string }) {
  const { t } = useTranslation();
  return (
    <div className="p-10">
      <h1 className="text-xl font-bold text-slate-900">{title}</h1>
      <p className="mt-1 text-sm text-slate-500">{t("placeholder.comingSoon")}</p>
    </div>
  );
}
