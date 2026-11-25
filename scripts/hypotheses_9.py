"""
hypotheses_9.py  v2
═══════════════════
9 исследовательских гипотез (10–18).
Оптимизировано: запросы agent_relations — per-run_id (Cloudflare 100s timeout).

Запуск:
    cd /Users/georgijtadziev/Documents/proga/diplom
    venv/bin/python scripts/hypotheses_9.py

Результат:
    data/plots/10_*..18_* (.png + .pdf)
    data/output/hypotheses_report.md
"""

from __future__ import annotations

import os, sys, textwrap, traceback, warnings
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import clickhouse_connect
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore")
matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
PLOTS_DIR  = ROOT / "data" / "plots"
OUTPUT_DIR = ROOT / "data" / "output"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DPI_PNG, DPI_PDF = 180, 140

EMOTION_AXES = [
    "sadness_joy", "fear_calm", "anger_humility",
    "disgust_acceptance", "habit_surprise",
    "shame_confidence", "alienation_openness",
]
EMOTION_RU = {
    "sadness_joy":"Печаль–Радость", "fear_calm":"Страх–Спокойствие",
    "anger_humility":"Гнев–Смирение", "disgust_acceptance":"Отвращение–Принятие",
    "habit_surprise":"Привычка–Удивление", "shame_confidence":"Стыд–Уверенность",
    "alienation_openness":"Отчуждение–Открытость",
}
INIT_TYPES = ["EMPTY", "RANDOM", "MIXED"]

SEM_RANGES = {
    # day_id в ClickHouse начинается с нуля: 0..1212 — 1213 дней.
    1: (0, 152), 2: (153, 302), 3: (303, 455), 4: (456, 605),
    5: (606, 758), 6: (759, 908), 7: (909, 1061), 8: (1062, 1212),
}
N_SEMESTERS = 8

def sem_start(s): return SEM_RANGES[s][0]
def sem_end(s):   return SEM_RANGES[s][1]
def get_sem(day):
    for s, (a, b) in SEM_RANGES.items():
        if a <= day <= b: return s
    return 8

def savefig(fig, name):
    png = PLOTS_DIR / f"{name}.png"
    pdf = PLOTS_DIR / f"{name}.pdf"
    fig.savefig(png, dpi=DPI_PNG, bbox_inches="tight")
    fig.savefig(pdf, dpi=DPI_PDF, bbox_inches="tight")
    plt.close(fig)
    return str(png)

def img_md(path, cap=""): return f"\n![{cap}]({os.path.relpath(path, OUTPUT_DIR)})\n*{cap}*\n"
def h2(t): return f"\n\n## {t}\n"
def h3(t): return f"\n### {t}\n"


class Hypotheses9:

    def __init__(self):
        host     = os.getenv("CLICKHOUSE_HOST", "db.georgytadjiev.ink")
        port     = int(os.getenv("CLICKHOUSE_PORT", "443"))
        user     = os.getenv("CLICKHOUSE_USER", "default")
        password = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass")
        secure   = os.getenv("CLICKHOUSE_SECURE", "True").lower() in ("true", "1", "yes")

        # На публичном endpoint Cloudflare режет запросы дольше ~100 с;
        # на локальном ClickHouse такого ограничения нет.
        read_timeout = 95 if secure else 600

        print("🔌  Подключение к ClickHouse…", flush=True)
        self.db = clickhouse_connect.get_client(
            host=host, port=port, username=user, password=password,
            secure=secure, autogenerate_session_id=False,
            connect_timeout=120, send_receive_timeout=read_timeout,
        )
        self._parts: List[str] = []
        self._ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.runs_df = self._load_meta()
        self.n_runs  = len(self.runs_df)
        self.max_day = int(self.q("SELECT max(day_id) FROM agent_states").iloc[0, 0])
        self.archetypes = sorted(self.q("SELECT DISTINCT archetype FROM agent_registry")["archetype"].tolist())

        # Деструктор (max отказов) и Медиатор (min отказов)
        arch_ref = self.q("""
            SELECT ar.archetype, round(countIf(i.type=0)/count()*100,1) AS pct
            FROM interactions i
            JOIN agent_registry ar ON i.run_id=ar.run_id AND i.to_id=ar.agent_id
            GROUP BY ar.archetype ORDER BY pct DESC
        """)
        self.destructor_name = arch_ref["archetype"].iloc[0]  if not arch_ref.empty else "Nihility"
        self.mediator_name   = arch_ref["archetype"].iloc[-1] if not arch_ref.empty else "Harmony"

        # Представительная выборка: по одному прогону из каждой серии
        self.sample_runs = self._pick_sample(per_family=1)

        print(f"✅  Подключение. Runs={self.n_runs}, max_day={self.max_day}", flush=True)
        print(f"   Архетипы: {self.archetypes}", flush=True)
        print(f"   Деструктор={self.destructor_name}, Медиатор={self.mediator_name}", flush=True)
        print(f"   Выборка для тяжёлых запросов: {len(self.sample_runs)} runs\n", flush=True)

    def q(self, sql):
        df = self.db.query_df(sql)
        if "run_id" in df.columns:
            df["run_id"] = df["run_id"].astype(str)
        return df

    def s(self, sql): return self.db.query_df(sql).iloc[0, 0]

    def _load_meta(self):
        df = self.q("SELECT run_id, scenario_name, run_name FROM simulation_runs ORDER BY scenario_name")
        def _init(n):
            upper = n.upper()
            for t in INIT_TYPES:
                if upper.endswith("_" + t): return t
            for t in INIT_TYPES:
                if ("_" + t) in upper: return t
            return "OTHER"
        df["init_type"] = df["scenario_name"].apply(_init)
        return df

    def _pick_sample(self, per_family=1):
        """Один прогон на каждую серию Run01–Run18, тип инициализации чередуется."""
        sample = []
        families = list(dict.fromkeys(self.runs_df["run_name"].tolist()))
        for i, family in enumerate(families):
            sub = self.runs_df[self.runs_df["run_name"] == family]
            wanted = INIT_TYPES[i % len(INIT_TYPES)]
            pick = sub[sub["init_type"] == wanted]
            if pick.empty:
                pick = sub
            sample.extend(pick["run_id"].tolist()[:per_family])
        if not sample:
            sample = self.runs_df["run_id"].tolist()
        return sample

    def _iter_relations(self, sql_template: str, run_ids=None, label=""):
        """Итерация по run_id для тяжёлых запросов agent_relations.
        sql_template должен содержать {rid} для подстановки."""
        results = []
        runs = run_ids or self.sample_runs
        for i, rid in enumerate(runs):
            print(f"     [{label}] run {i+1}/{len(runs)}…", flush=True, end="\r")
            try:
                df = self.q(sql_template.format(rid=rid))
                if not df.empty:
                    df["run_id"] = str(rid)
                    results.append(df)
            except Exception as e:
                print(f"     [{label}] run {i+1} — ошибка: {e}", flush=True)
        print(f"     [{label}] done, {len(results)} runs OK       ", flush=True)
        return pd.concat(results, ignore_index=True) if results else pd.DataFrame()

    # ════════════════════════════════════════════════════════
    #  Г10 — ЭФФЕКТ ВОСКРЕСНОГО СБРОСА
    # ════════════════════════════════════════════════════════

    def h10_sunday_reset(self) -> str:
        print("[10/18] Эффект воскресного сброса…", flush=True)
        rep = h2("10. «Эффект воскресного сброса»")
        rep += ("\n**Гипотеза:** Хронически депрессивные агенты восстанавливаются "
                "после воскресного δ-сдвига медленнее нейтральных.\n")

        baseline_end = 6     # классификация до первого воскресного сдвига
        profile_end = 140    # профиль по неделям в пределах 1-го семестра
        NEG_THR, POS_THR = -5.0, 5.0
        axes_sum = " + ".join(EMOTION_AXES)

        # Классификация как в отдельном анализе воскресного сброса:
        # среднее по всем 7 осям за дни 1–6, до первого сброса.
        agent_bl = self.q(f"""
            SELECT run_id, agent_id, avg(({axes_sum}) / 7.0) AS bl_mood
            FROM agent_states WHERE day_id BETWEEN 1 AND {baseline_end}
            GROUP BY run_id, agent_id
        """)

        n_neg = int((agent_bl["bl_mood"] < NEG_THR).sum())
        n_pos = int((agent_bl["bl_mood"] > POS_THR).sum())
        n_neu = len(agent_bl) - n_neg - n_pos

        df_week = self.q(f"""
            WITH baseline AS (
                SELECT run_id, agent_id, avg(({axes_sum}) / 7.0) AS bm
                FROM agent_states WHERE day_id BETWEEN 1 AND {baseline_end}
                GROUP BY run_id, agent_id
            )
            SELECT s.day_id % 7 AS dow,
                   avgIf(s.sadness_joy, b.bm < {NEG_THR})  AS neg_joy,
                   avgIf(s.sadness_joy, b.bm > {POS_THR})  AS pos_joy,
                   avgIf(s.sadness_joy, b.bm >= {NEG_THR} AND b.bm <= {POS_THR}) AS neu_joy,
                   count() AS n
            FROM agent_states s
            JOIN baseline b ON s.run_id=b.run_id AND s.agent_id=b.agent_id
            WHERE s.day_id BETWEEN 1 AND {profile_end}
            GROUP BY dow ORDER BY dow
        """)

        day_labels = ["Пн","Вт","Ср","Чт","Пт","Сб"]
        fig, axes = plt.subplots(1, 2, figsize=(15, 5))

        ax = axes[0]
        ax.hist(agent_bl["bl_mood"], bins=60, color="#1565C0", edgecolor="white", alpha=.8)
        ax.axvline(NEG_THR, color="red", lw=2, ls="--", label=f"Порог ({NEG_THR})")
        ax.axvline(POS_THR, color="green", lw=2, ls="--", label=f"Порог ({POS_THR})")
        ax.set_title(f"Базовый уровень настроения (дни 1–{baseline_end})\n"
                     f"Негат: {n_neg:,} | Нейтр: {n_neu:,} | Позит: {n_pos:,}",
                     fontsize=10, fontweight="bold")
        ax.set_xlabel("среднее по 7 осям"); ax.set_ylabel("Кол-во"); ax.legend(fontsize=8)

        ax = axes[1]
        if not df_week.empty:
            x = df_week["dow"].values
            ax.plot(x, df_week["neg_joy"], "o-", color="#EF5350", lw=2, ms=7,
                    label=f"Депрессивные (<{NEG_THR})")
            ax.plot(x, df_week["pos_joy"], "s-", color="#4CAF50", lw=2, ms=7,
                    label=f"Позитивные (>{POS_THR})")
            ax.plot(x, df_week["neu_joy"], "^-", color="#FF9800", lw=2, ms=7,
                    label="Нейтральные")
            ax.axhline(0, color="grey", lw=.8, ls=":")
            ax.set_xticks(range(1, 7)); ax.set_xticklabels(day_labels)
            ax.set_title(f"sadness_joy по дням недели (дни 1–{profile_end})",
                         fontsize=10, fontweight="bold")
            ax.set_xlabel("День недели"); ax.set_ylabel("Среднее"); ax.legend(fontsize=8)
        fig.tight_layout(); p10 = savefig(fig, "10_sunday_reset")

        rep += img_md(p10, "Воскресный сброс: базовый уровень и профиль по дням")
        rep += (f"\n- Негативные (<{NEG_THR}): {n_neg:,}\n"
                f"- Позитивные (>{POS_THR}): {n_pos:,}\n- Нейтральные: {n_neu:,}\n")
        if not df_week.empty:
            for col, name in [("neg_joy","Депр."),("pos_joy","Позит."),("neu_joy","Нейтр.")]:
                v = df_week[col].dropna()
                if len(v) >= 2:
                    rep += f"- {name}: размах = {v.max()-v.min():.2f}\n"
        return rep

    # ════════════════════════════════════════════════════════
    #  Г11 — ЗАКОН ПРОЩЕНИЯ
    # ════════════════════════════════════════════════════════

    def h11_forgiveness_law(self) -> str:
        print("[11/18] Закон прощения…", flush=True)
        rep = h2("11. «Закон прощения» — асимметрия затухания")
        rep += ("\n**Гипотеза:** Положительные связи затухают с 0.5·d, "
                "отрицательные — с полным d.\n")

        # Per-run запросы, сэмплируем каждый 60-й день
        df = self._iter_relations("""
            SELECT ar.archetype,
                   rel.day_id,
                   avgIf(rel.trust, rel.trust > 0)  AS avg_pos,
                   avgIf(rel.trust, rel.trust < 0)  AS avg_neg,
                   countIf(rel.trust > 0)            AS n_pos,
                   countIf(rel.trust < 0)            AS n_neg
            FROM agent_relations rel
            JOIN agent_registry ar ON ar.run_id = '{rid}' AND rel.subject_id = ar.agent_id
            WHERE rel.run_id = '{rid}' AND rel.day_id % 60 = 0
            GROUP BY ar.archetype, rel.day_id
            ORDER BY ar.archetype, rel.day_id
        """, label="H11")

        if df.empty:
            return rep + "\n*Нет данных в agent_relations.*\n"

        archetypes = sorted(df["archetype"].unique())
        palette = sns.color_palette("tab10", len(archetypes))
        arch_color = dict(zip(archetypes, palette))

        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        slopes = []
        for arch in archetypes:
            sub = df[df["archetype"] == arch].copy()
            sub["sem"] = sub["day_id"].apply(get_sem)
            agg = sub.groupby("sem")[["avg_pos","avg_neg"]].mean().dropna()
            if len(agg) < 3: continue
            axes[0].plot(agg.index, agg["avg_pos"], color=arch_color[arch],
                         lw=1.5, marker="o", ms=4, label=arch)
            axes[1].plot(agg.index, agg["avg_neg"].abs(), color=arch_color[arch],
                         lw=1.5, marker="o", ms=4, label=arch)
            sl_p = stats.linregress(agg.index, agg["avg_pos"]).slope
            sl_n = stats.linregress(agg.index, agg["avg_neg"].abs()).slope
            ratio = abs(sl_n / sl_p) if abs(sl_p) > 1e-6 else float("nan")
            slopes.append({"Архетип": arch, "Δ поз./сем": round(sl_p, 4),
                           "Δ |нег.|/сем": round(sl_n, 4), "|нег/поз|": round(ratio, 2)})

        for ax, t in [(axes[0],"Средний позитивный trust"),(axes[1],"Средний |негативный trust|")]:
            ax.set_title(t, fontsize=11, fontweight="bold")
            ax.set_xlabel("Семестр"); ax.set_ylabel("Trust")
            ax.set_xticks(range(1, N_SEMESTERS+1)); ax.legend(fontsize=7, ncol=2)
        fig.suptitle("Закон прощения", fontsize=12, fontweight="bold")
        fig.tight_layout(); p11 = savefig(fig, "11_forgiveness_law")

        rep += img_md(p11, "Асимметрия затухания: позитивные vs негативные связи")
        rep += "\n" + pd.DataFrame(slopes).to_markdown(index=False) + "\n"
        rep += "\n*|нег/поз| > 1 ⇒ закон прощения подтверждён.*\n"
        return rep

    # ════════════════════════════════════════════════════════
    #  Г12 — СЕМЕСТРОВАЯ АМНЕЗИЯ
    # ════════════════════════════════════════════════════════

    def h12_semester_amnesia(self) -> str:
        print("[12/18] Семестровая амнезия…", flush=True)
        rep = h2("12. «Семестровая амнезия»")
        rep += ("\n**Гипотеза:** Агенты с высоким trust быстрее восстанавливают "
                "эмоциональный ранг после семестрового сброса.\n")

        rank_data = []
        day_notes = []
        for sem in range(2, N_SEMESTERS + 1):
            ss  = sem_start(sem)
            spe = ss - 1
            print(f"     Семестр {sem}…", flush=True)

            # Trust перед сбросом — per-run
            df_trust = self._iter_relations(f"""
                SELECT subject_id AS agent_id, avg(trust) AS avg_trust
                FROM agent_relations
                WHERE run_id = '{{rid}}' AND day_id BETWEEN {spe-4} AND {spe}
                GROUP BY subject_id
            """, label=f"S{sem}-trust", run_ids=self.sample_runs)
            if df_trust.empty: continue

            df_before = self.q(f"""
                SELECT run_id, agent_id, avg(sadness_joy) AS joy_before
                FROM agent_states WHERE day_id BETWEEN {spe-4} AND {spe}
                GROUP BY run_id, agent_id
            """)
            if df_before.empty: continue

            for offset in [1, 7, 30]:
                tday = ss + offset - 1
                if tday > self.max_day: continue
                df_after = self.q(f"""
                    SELECT run_id, agent_id, sadness_joy AS joy_after
                    FROM agent_states WHERE day_id = {tday}
                """)
                if df_after.empty:
                    # Воскресенья и каникулы не пишутся в agent_states.
                    # Если целевой день пропущен, берём ближайший следующий.
                    nxt = self.q(
                        f"SELECT min(day_id) AS d FROM agent_states WHERE day_id > {tday}"
                    )
                    if nxt.empty or pd.isna(nxt["d"].iloc[0]): continue
                    actual = int(nxt["d"].iloc[0])
                    df_after = self.q(f"""
                        SELECT run_id, agent_id, sadness_joy AS joy_after
                        FROM agent_states WHERE day_id = {actual}
                    """)
                    if df_after.empty: continue
                    day_notes.append((sem, offset, actual))

                merged = (df_trust.merge(df_before, on=["run_id","agent_id"], how="inner")
                                  .merge(df_after, on=["run_id","agent_id"], how="inner"))
                if len(merged) < 30: continue
                merged["rb"] = merged.groupby("run_id")["joy_before"].rank()
                merged["ra"] = merged.groupby("run_id")["joy_after"].rank()
                tq25 = merged["avg_trust"].quantile(.25)
                tq75 = merged["avg_trust"].quantile(.75)

                for gn, mask in [("Высокий trust", merged["avg_trust"] >= tq75),
                                 ("Низкий trust",  merged["avg_trust"] <= tq25)]:
                    sub = merged[mask]
                    if len(sub) < 10: continue
                    rho, pv = stats.spearmanr(sub["rb"], sub["ra"])
                    rank_data.append({"Сем": sem, "Дней": offset,
                                      "Группа": gn, "ρ": round(rho,3), "p": round(pv,6)})

        if not rank_data:
            return rep + "\n*Недостаточно данных.*\n"

        df_r = pd.DataFrame(rank_data)
        fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
        cg = {"Высокий trust": "#4CAF50", "Низкий trust": "#EF5350"}
        for ax, off in [(axes[0], 7), (axes[1], 30)]:
            sub = df_r[df_r["Дней"] == off]
            for g, gdf in sub.groupby("Группа"):
                ax.plot(gdf["Сем"], gdf["ρ"], marker="o", lw=2, color=cg.get(g,"#999"), label=g)
            ax.axhline(0.3, color="green", lw=1, ls="--", alpha=.5)
            ax.set_title(f"День {off} после сброса", fontweight="bold")
            ax.set_xlabel("Семестр"); ax.set_ylabel("ρ Спирмена"); ax.legend(fontsize=8)
        fig.suptitle("Семестровая амнезия", fontsize=12, fontweight="bold")
        fig.tight_layout(); p12 = savefig(fig, "12_semester_amnesia")

        rep += img_md(p12, "Ранговая корреляция до/после сброса")
        rep += "\n" + df_r.to_markdown(index=False) + "\n"
        if day_notes:
            notes = ", ".join(f"С{s} +{o} → день {d}" for s, o, d in day_notes)
            rep += (f"\n*Воскресенья и каникулы не пишутся в `agent_states`. "
                    f"Где целевой день пропущен, взят ближайший следующий: {notes}.*\n")
        return rep

    # ════════════════════════════════════════════════════════
    #  Г13 — ЛОВУШКА ЛОГАРИФМА
    # ════════════════════════════════════════════════════════

    def h13_log_trap(self) -> str:
        print("[13/18] Ловушка логарифма…", flush=True)
        rep = h2("13. «Ловушка логарифма»")
        rep += ("\n**Гипотеза:** Архетипы с log(U) в формуле приоритета "
                "создают бимодальную структуру utility.\n")

        keywords = ["erudition", "trailblaz", "nihility"]
        log_archs = [a for a in self.archetypes if any(k in a.lower() for k in keywords)]
        if not log_archs: log_archs = self.archetypes[:2]
        log_list = ",".join([f"'{a}'" for a in log_archs])
        rep += f"\n*Log-архетипы: {log_archs}*\n"

        # Per-run, сэмплируем каждый 10-й день
        df = self._iter_relations(f"""
            SELECT ar.archetype,
                   multiIf(ar.archetype IN ({log_list}), 'log', 'other') AS grp,
                   rel.utility
            FROM interactions i
            JOIN agent_registry ar ON ar.run_id = '{{rid}}' AND i.from_id = ar.agent_id
            JOIN agent_relations rel
                ON rel.run_id = '{{rid}}' AND rel.day_id = i.day_id
               AND rel.slot_id = 9 AND rel.subject_id = i.from_id AND rel.object_id = i.to_id
            WHERE i.run_id = '{{rid}}' AND i.day_id % 10 = 0
            LIMIT 200000
        """, label="H13", run_ids=self.sample_runs)

        if df.empty:
            return rep + "\n*Нет данных.*\n"

        df_log = df[df["grp"] == "log"]
        df_oth = df[df["grp"] == "other"]
        rep += f"\n*Строк: log={len(df_log):,}, other={len(df_oth):,}*\n"

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        for ax, data, title in [(axes[0], df_log, f"Log ({', '.join(log_archs)})"),
                                 (axes[1], df_oth, "Остальные")]:
            if data.empty:
                ax.text(.5,.5, "Нет данных", ha="center", va="center", transform=ax.transAxes)
            else:
                for a in data["archetype"].unique():
                    ax.hist(data[data["archetype"]==a]["utility"], bins=60, alpha=.4, density=True, label=a)
            ax.axvline(0, color="red", lw=2, ls="--")
            ax.set_title(title, fontweight="bold"); ax.set_xlabel("Utility"); ax.legend(fontsize=7, ncol=2)
        fig.suptitle("Распределение utility при взаимодействии", fontsize=12, fontweight="bold")
        fig.tight_layout(); p13 = savefig(fig, "13_log_trap")

        def bimod(x):
            n=len(x); sk=stats.skew(x); ku=stats.kurtosis(x)
            return (sk**2+1) / (ku + 3*(n-1)**2/((n-2)*(n-3)))
        bm_l = bimod(df_log["utility"].dropna().values) if len(df_log) > 10 else float("nan")
        bm_o = bimod(df_oth["utility"].dropna().values) if len(df_oth) > 10 else float("nan")

        rep += img_md(p13, "Бимодальность utility")
        rep += (f"\n- Бимодальность log: **{bm_l:.3f}**\n"
                f"- Бимодальность ост.: **{bm_o:.3f}**\n- Порог: >0.555\n")
        return rep

    # ════════════════════════════════════════════════════════
    #  Г14 — НОНКОНФОРМИСТ × МЕДИАТОР
    # ════════════════════════════════════════════════════════

    def h14_nonconf_mediator(self) -> str:
        print("[14/18] Нонконформист × Медиатор…", flush=True)
        rep = h2(f"14. Матрица отказов и доверия")

        # Матрица отказов — таблица interactions (148M, OK без per-run)
        df_ref = self.q("""
            SELECT ar1.archetype AS arch_init, ar2.archetype AS arch_targ,
                   round(countIf(i.type=0)/count()*100,2) AS pct
            FROM interactions i
            JOIN agent_registry ar1 ON i.run_id=ar1.run_id AND i.from_id=ar1.agent_id
            JOIN agent_registry ar2 ON i.run_id=ar2.run_id AND i.to_id=ar2.agent_id
            GROUP BY arch_init, arch_targ
        """)

        pivot_ref = df_ref.pivot_table(index="arch_init", columns="arch_targ",
                                       values="pct", aggfunc="mean").fillna(0)

        # Trust — per-run
        df_trust = self._iter_relations(f"""
            SELECT ar1.archetype AS subj, ar2.archetype AS obj,
                   avg(rel.trust) AS avg_trust
            FROM agent_relations rel
            JOIN agent_registry ar1 ON ar1.run_id='{{rid}}' AND rel.subject_id=ar1.agent_id
            JOIN agent_registry ar2 ON ar2.run_id='{{rid}}' AND rel.object_id=ar2.agent_id
            WHERE rel.run_id='{{rid}}' AND rel.day_id >= {self.max_day - 5}
            GROUP BY subj, obj
        """, label="H14-trust")

        fig, axes = plt.subplots(1, 2, figsize=(20, 8))
        sns.heatmap(pivot_ref, ax=axes[0], cmap="Reds", annot=True, fmt=".1f",
                    linewidths=.5, cbar_kws={"label": "% отказов"})
        axes[0].set_title("Матрица отказов (%)", fontsize=11, fontweight="bold")

        if not df_trust.empty:
            pivot_t = df_trust.groupby(["subj","obj"])["avg_trust"].mean().reset_index()
            pivot_t = pivot_t.pivot_table(index="subj", columns="obj",
                                          values="avg_trust").fillna(0)
            sns.heatmap(pivot_t, ax=axes[1], cmap="RdYlGn", center=0, annot=True, fmt=".1f",
                        linewidths=.5, cbar_kws={"label": "Trust"})
        axes[1].set_title("Финальный Trust", fontsize=11, fontweight="bold")
        fig.suptitle("Межархетипные отказы и доверие", fontsize=13, fontweight="bold")
        fig.tight_layout(); p14 = savefig(fig, "14_nonconf_mediator")

        rep += img_md(p14, "Матрицы отказов и Trust")
        return rep

    # ════════════════════════════════════════════════════════
    #  Г15 — ОППОРТУНИСТ В СПОРТЗАЛЕ
    # ════════════════════════════════════════════════════════

    def h15_gym_clustering(self) -> str:
        print("[15/18] Кластеризация GYM…", flush=True)
        rep = h2("15. «Оппортунист в спортзале»")

        try: import networkx as nx
        except ImportError: return rep + "\n*networkx не установлен.*\n"

        # Per-run запросы (interactions 148M с 2 JOIN таймаутит)
        gym_parts = []
        for i, rid in enumerate(self.sample_runs):
            print(f"     [H15] run {i+1}/{len(self.sample_runs)}…", flush=True, end="\r")
            try:
                df = self.q(f"""
                    SELECT ar1.archetype AS arch1, ar2.archetype AS arch2,
                           greatest(i.from_id,i.to_id) AS a, least(i.from_id,i.to_id) AS b,
                           count() AS weight
                    FROM interactions i
                    JOIN agent_registry ar1 ON ar1.run_id='{rid}' AND i.from_id=ar1.agent_id
                    JOIN agent_registry ar2 ON ar2.run_id='{rid}' AND i.to_id=ar2.agent_id
                    WHERE i.run_id='{rid}' AND i.slot_id = 8
                    GROUP BY arch1, arch2, a, b
                """)
                if not df.empty:
                    df["run_id"] = str(rid)
                    gym_parts.append(df)
            except Exception as e:
                print(f"     [H15] run {i+1} ошибка: {e}", flush=True)
        print(f"     [H15] done, {len(gym_parts)} runs       ", flush=True)

        if not gym_parts: return rep + "\n*Нет GYM данных.*\n"
        df_gym = pd.concat(gym_parts, ignore_index=True)

        archetypes = sorted(df_gym["arch1"].unique())
        results = []
        for arch in archetypes:
            sub = df_gym[(df_gym["arch1"]==arch)|(df_gym["arch2"]==arch)]
            run_c = []
            for rid, grp in sub.groupby("run_id"):
                G = nx.Graph()
                for _, r in grp.iterrows(): G.add_edge(r["a"], r["b"], weight=r["weight"])
                if len(G.nodes) < 5: continue
                run_c.append({"c": nx.average_clustering(G),
                              "d": np.mean([d for _,d in G.degree()]), "n": len(G.nodes)})
            if not run_c: continue
            rc = pd.DataFrame(run_c)
            results.append({"Архетип": arch, "Кластеризация": round(rc["c"].mean(),4),
                            "Ср. степень": round(rc["d"].mean(),2), "Вершин": int(rc["n"].mean())})

        dc = pd.DataFrame(results).sort_values("Кластеризация", ascending=False)
        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.bar(dc["Архетип"], dc["Кластеризация"],
                      color=sns.color_palette("coolwarm_r", len(dc)), edgecolor="white")
        for b, v in zip(bars, dc["Кластеризация"]):
            ax.text(b.get_x()+b.get_width()/2, b.get_height()+.002, f"{v:.3f}", ha="center", fontsize=9)
        ax.set_title("Кластеризация GYM-сети", fontsize=12, fontweight="bold")
        ax.tick_params(axis="x", rotation=35); fig.tight_layout()
        p15 = savefig(fig, "15_gym_clustering")

        rep += img_md(p15, "Кластеризация GYM")
        rep += "\n" + dc.to_markdown(index=False) + "\n"
        return rep

    # ════════════════════════════════════════════════════════
    #  Г16 — ТЁПЛЫЕ ОСТРОВА
    # ════════════════════════════════════════════════════════

    def h16_warm_islands(self) -> str:
        print("[16/18] Тёплые острова…", flush=True)
        rep = h2("16. «Тёплые острова»")

        try: import networkx as nx
        except ImportError: return rep + "\n*networkx не установлен.*\n"

        # Per-run: trust ≥ 70 на последний день
        df_edges = self._iter_relations(f"""
            SELECT subject_id, object_id, avg(trust) AS avg_trust
            FROM agent_relations
            WHERE run_id = '{{rid}}' AND day_id = {self.max_day} AND trust >= 70
            GROUP BY subject_id, object_id
        """, label="H16")

        if df_edges.empty: return rep + "\n*Нет рёбер trust≥70.*\n"

        df_reg = self.q("SELECT run_id, agent_id, archetype FROM agent_registry")
        reg = {(str(r["run_id"]), r["agent_id"]): r["archetype"] for _, r in df_reg.iterrows()}

        comp_stats, all_sizes = [], []
        for rid, grp in df_edges.groupby("run_id"):
            G = nx.Graph()
            for _, r in grp.iterrows(): G.add_edge(r["subject_id"], r["object_id"])
            for comp in nx.connected_components(G):
                if len(comp) < 3: continue
                all_sizes.append(len(comp))
                ac = {}
                for nd in comp:
                    a = reg.get((rid, nd), "?"); ac[a] = ac.get(a, 0) + 1
                dom = max(ac, key=ac.get)
                comp_stats.append({"Размер": len(comp), "Доминант": dom,
                                   "Доля(%)": round(ac[dom]/len(comp)*100, 1)})

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        axes[0].hist(all_sizes, bins=30, color="#1565C0", edgecolor="white")
        axes[0].set_title("Распределение размеров (trust≥70)", fontweight="bold")
        if comp_stats:
            dc = pd.DataFrame(comp_stats)["Доминант"].value_counts()
            axes[1].bar(dc.index, dc.values, color=sns.color_palette("Set2", len(dc)), edgecolor="white")
            axes[1].set_title("Доминирующий архетип", fontweight="bold")
            axes[1].tick_params(axis="x", rotation=35)
        fig.suptitle("Тёплые острова", fontsize=12, fontweight="bold")
        fig.tight_layout(); p16 = savefig(fig, "16_warm_islands")

        rep += img_md(p16, "Тёплые острова")
        rep += f"\n**Кластеров (≥3): {len(all_sizes)}**\n\n"
        if comp_stats:
            rep += pd.DataFrame(comp_stats).sort_values("Размер", ascending=False).head(15).to_markdown(index=False) + "\n"
        return rep

    # ════════════════════════════════════════════════════════
    #  Г17 — ДЕСТРУКТОР-КАТАЛИЗАТОР
    # ════════════════════════════════════════════════════════

    def h17_destructor_catalyst(self) -> str:
        print("[17/18] Деструктор-катализатор…", flush=True)
        rep = h2(f"17. «{self.destructor_name}» как катализатор распада")

        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
        except ImportError: return rep + "\n*scikit-learn не установлен.*\n"

        # Per-run запросы (GROUP BY greatest/least по 148M таймаутит)
        pair_parts = []
        for i, rid in enumerate(self.sample_runs):
            print(f"     [H17] run {i+1}/{len(self.sample_runs)}…", flush=True, end="\r")
            try:
                df_b = self.q(f"""
                    SELECT greatest(from_id,to_id) AS a, least(from_id,to_id) AS b,
                           max(day_id) AS last_day,
                           if(max(day_id) < {self.max_day - 200} AND max(day_id) > 200, 1, 0) AS broken
                    FROM interactions WHERE run_id = '{rid}'
                    GROUP BY a, b
                    HAVING last_day > 200
                    LIMIT 20000
                """)
                if not df_b.empty:
                    df_b["run_id"] = str(rid)
                    pair_parts.append(df_b)
            except Exception as e:
                print(f"     [H17] run {i+1} ошибка: {e}", flush=True)
        print(f"     [H17] pairs done, {len(pair_parts)} runs       ", flush=True)
        if not pair_parts:
            return rep + "\n*Недостаточно данных.*\n"
        df_all = pd.concat(pair_parts, ignore_index=True)
        if len(df_all) < 100: return rep + "\n*Недостаточно данных.*\n"

        df_destr = self.q(f"""
            SELECT i.run_id, i.to_id AS agent_id, countIf(i.type=0) AS dr
            FROM interactions i
            JOIN agent_registry ar ON i.run_id=ar.run_id AND i.from_id=ar.agent_id
            WHERE ar.archetype = '{self.destructor_name}'
            GROUP BY i.run_id, agent_id
        """)
        df_all = df_all.merge(df_destr.rename(columns={"agent_id":"a","dr":"dr_a"}),
                              on=["run_id","a"], how="left").fillna(0)

        X = df_all[["dr_a"]].values; y = df_all["broken"].values
        X_sc = StandardScaler().fit_transform(X)
        lr = LogisticRegression(max_iter=300).fit(X_sc, y)
        coef = float(lr.coef_[0][0]); odds = np.exp(coef)

        fig, ax = plt.subplots(figsize=(9, 5))
        for v, l, c in [(1,"Распавшиеся","#EF5350"),(0,"Устойчивые","#4CAF50")]:
            ax.hist(df_all[df_all["broken"]==v]["dr_a"], bins=40, alpha=.6, density=True, label=l, color=c)
        ax.set_title(f"Отказы от {self.destructor_name}", fontweight="bold")
        ax.set_xlabel("Отказов"); ax.set_ylabel("Плотность"); ax.legend()
        fig.tight_layout(); p17 = savefig(fig, "17_destructor_catalyst")

        rep += img_md(p17, "Деструктор-катализатор")
        rep += (f"\n- β (станд.): **{coef:.3f}**\n- OR: **{odds:.3f}**\n"
                f"- {'✅ Значимый эффект' if odds > 1.05 else '❌ Незначим'}\n")
        return rep

    # ════════════════════════════════════════════════════════
    #  Г18 — ЭФФЕКТ ПЕРВОГО СЕМЕСТРА
    # ════════════════════════════════════════════════════════

    def h18_first_semester(self) -> str:
        print("[18/18] Эффект первого семестра…", flush=True)
        rep = h2("18. «Эффект первого семестра» — path dependency")

        empty_runs = self.runs_df[self.runs_df["init_type"]=="EMPTY"]["run_id"].tolist()
        if not empty_runs: return rep + "\n*Нет EMPTY-сценариев.*\n"
        run_filter = ",".join([f"'{r}'" for r in empty_runs])
        s1s, s1e = SEM_RANGES[1]; s8s, s8e = SEM_RANGES[8]

        df = self.q(f"""
            SELECT run_id, from_id AS agent_id,
                   countIf(day_id BETWEEN {s1s} AND {s1e}) AS cnt_s1,
                   countIf(day_id BETWEEN {s8s} AND {s8e}) AS cnt_s8
            FROM interactions WHERE run_id IN ({run_filter})
            GROUP BY run_id, agent_id
            HAVING cnt_s1 > 0 AND cnt_s8 > 0
        """)
        if df.empty: return rep + "\n*Нет данных.*\n"

        df["r1"] = df.groupby("run_id")["cnt_s1"].rank()
        df["r8"] = df.groupby("run_id")["cnt_s8"].rank()
        rho, p = stats.spearmanr(df["r1"], df["r8"])

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        axes[0].scatter(df["r1"], df["r8"], alpha=.15, s=6, color="#1565C0")
        z = np.polyfit(df["r1"], df["r8"], 1)
        xl = np.linspace(df["r1"].min(), df["r1"].max(), 100)
        axes[0].plot(xl, np.poly1d(z)(xl), "r-", lw=2)
        axes[0].set_title(f"С1 vs С8: ρ={rho:.3f}, p={p:.4f}", fontweight="bold")
        axes[0].set_xlabel("Ранг С1"); axes[0].set_ylabel("Ранг С8")

        top10 = df[df["r1"] <= df["r1"].quantile(.1)]
        axes[1].hist(top10["r8"]/df["r8"].max()*100, bins=30, color="#E65100", edgecolor="white")
        axes[1].axvline(10, color="green", lw=2, ls="--", label="ТОП-10%")
        axes[1].set_title("ТОП-10% С1 → С8", fontweight="bold"); axes[1].legend()
        fig.tight_layout(); p18 = savefig(fig, "18_first_semester")

        rep += img_md(p18, "Path dependency")
        rep += (f"\n- ρ = **{rho:.3f}**, p = {p:.6f}\n"
                f"- {'✅ Path dependency' if rho > .3 else '❌ Нет зависимости'}\n")
        return rep

    # ════════════════════════════════════════════════════════

    def run_all(self):
        print("\n" + "═"*60 + "\n  ГИПОТЕЗЫ 10–18\n" + "═"*60 + "\n")
        for num, fn in [("10", self.h10_sunday_reset), ("11", self.h11_forgiveness_law),
                        ("12", self.h12_semester_amnesia), ("13", self.h13_log_trap),
                        ("14", self.h14_nonconf_mediator), ("15", self.h15_gym_clustering),
                        ("16", self.h16_warm_islands), ("17", self.h17_destructor_catalyst),
                        ("18", self.h18_first_semester)]:
            try:
                self._parts.append(fn())
                print(f"  ✅ Гипотеза {num}\n", flush=True)
            except Exception:
                err = traceback.format_exc()
                print(f"  ⚠️  Гипотеза {num}:\n{err}\n", flush=True)
                self._parts.append(f"\n## Гипотеза {num} — ошибка\n```\n{err}\n```\n")
        self._save_report()

    def _save_report(self):
        header = textwrap.dedent(f"""
            # Отчёт: Гипотезы 10–18
            **Дата:** {self._ts} | **Runs:** {self.n_runs} | **max_day:** {self.max_day}
            **Архетипы:** {', '.join(self.archetypes)}
            ---
        """).strip()
        path = OUTPUT_DIR / "hypotheses_report.md"
        path.write_text(header + "\n" + "\n".join(self._parts), encoding="utf-8")
        print(f"\n📝  {path}\n📊  {PLOTS_DIR.resolve()}\n" + "═"*60)

if __name__ == "__main__":
    Hypotheses9().run_all()
