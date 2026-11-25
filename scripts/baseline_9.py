"""
baseline_9.py
═════════════
Переработанный скрипт для 9 базовых блоков анализа (01–09).
Все вычисления — на стороне ClickHouse; в Python — только визуализация.

Запуск:
    cd /Users/georgijtadziev/Documents/proga/diplom
    venv/bin/python scripts/baseline_9.py

Результат:
    data/plots/01_*..09_* (.png + .pdf)
    data/output/baseline_report.md
"""

from __future__ import annotations

import os
import sys
import textwrap
import traceback
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import clickhouse_connect
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore")
matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["axes.unicode_minus"] = False

# ══════════════════════════════════════════════════════════════
#  КОНФИГУРАЦИЯ
# ══════════════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parent.parent
PLOTS_DIR  = ROOT / "data" / "plots"
OUTPUT_DIR = ROOT / "data" / "output"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DPI_PNG = 180
DPI_PDF = 140

EMOTION_AXES = [
    "sadness_joy", "fear_calm", "anger_humility",
    "disgust_acceptance", "habit_surprise",
    "shame_confidence", "alienation_openness",
]
EMOTION_RU = {
    "sadness_joy":        "Печаль–Радость",
    "fear_calm":          "Страх–Спокойствие",
    "anger_humility":     "Гнев–Смирение",
    "disgust_acceptance": "Отвращение–Принятие",
    "habit_surprise":     "Привычка–Удивление",
    "shame_confidence":   "Стыд–Уверенность",
    "alienation_openness":"Отчуждение–Открытость",
}

INIT_TYPES = ["EMPTY", "RANDOM", "MIXED"]
C3 = ["#2196F3", "#FF9800", "#4CAF50"]

SEM_RANGES = {
    # day_id в ClickHouse начинается с нуля: 0..1212 — 1213 дней.
    1: (0, 152), 2: (153, 302), 3: (303, 455), 4: (456, 605),
    5: (606, 758), 6: (759, 908), 7: (909, 1061), 8: (1062, 1212),
}
N_SEMESTERS = 8

def sem_start(s: int) -> int: return SEM_RANGES[s][0]
def sem_end(s: int) -> int: return SEM_RANGES[s][1]
def get_sem(day: int) -> int:
    for s, (a, b) in SEM_RANGES.items():
        if a <= day <= b: return s
    return 8

# ══════════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ══════════════════════════════════════════════════════════════

def savefig(fig: plt.Figure, name: str) -> str:
    png = PLOTS_DIR / f"{name}.png"
    pdf = PLOTS_DIR / f"{name}.pdf"
    fig.savefig(png, dpi=DPI_PNG, bbox_inches="tight")
    fig.savefig(pdf, dpi=DPI_PDF, bbox_inches="tight")
    plt.close(fig)
    return str(png)

def img_md(path: str, cap: str = "") -> str:
    rel = os.path.relpath(path, OUTPUT_DIR)
    return f"\n![{cap}]({rel})\n*{cap}*\n"

def h2(t: str) -> str: return f"\n\n## {t}\n"
def h3(t: str) -> str: return f"\n### {t}\n"


# ══════════════════════════════════════════════════════════════
#  КЛАСС
# ══════════════════════════════════════════════════════════════

class Baseline9:

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

        # Мета
        self.runs_df = self._load_meta()
        self.n_runs  = len(self.runs_df)
        self.max_day = int(self.q("SELECT max(day_id) FROM agent_states").iloc[0, 0])
        self.archetypes = sorted(self.q("SELECT DISTINCT archetype FROM agent_registry")["archetype"].tolist())

        # Представительная выборка для тяжёлых запросов
        self.sample_runs = self._pick_sample(per_family=1)

        print(f"✅  Подключение установлено.", flush=True)
        print(f"   Сценариев: {self.n_runs}, max_day: {self.max_day}", flush=True)
        print(f"   Архетипов: {len(self.archetypes)}: {self.archetypes}", flush=True)
        print(f"   Выборка: {len(self.sample_runs)} runs", flush=True)
        print()

    def q(self, sql: str) -> pd.DataFrame:
        df = self.db.query_df(sql)
        # ClickHouse отдаёт UUID-объекты, а per-run выборки хранят run_id
        # строкой. Приводим к строке, чтобы merge по run_id не терял строки.
        if "run_id" in df.columns:
            df["run_id"] = df["run_id"].astype(str)
        return df

    def s(self, sql: str):
        return self.db.query_df(sql).iloc[0, 0]

    def _load_meta(self) -> pd.DataFrame:
        df = self.q("SELECT run_id, scenario_name, run_name, start_time FROM simulation_runs ORDER BY scenario_name")
        def _init(n):
            upper = n.upper()
            for t in INIT_TYPES:
                if upper.endswith("_" + t): return t
            for t in INIT_TYPES:
                if ("_" + t) in upper: return t
            return "OTHER"
        def _group(n):
            try:
                prefix = n.split("_")[0].replace("RUN", "Run")
                homogeneous = {f"Run{i:02d}" for i in range(1, 8)}
                homogeneous.update({"Run15", "Run16"})
                return "Гомогенные" if prefix in homogeneous else "Гетерогенные"
            except Exception:
                return "Неизвестно"
        df["init_type"] = df["scenario_name"].apply(_init)
        df["group"]     = df["run_name"].apply(_group)
        return df

    def _pick_sample(self, per_family=1):
        """Один прогон на каждую серию сценариев.

        Первые три сценария подряд — это Run01–Run03, то есть только
        Erudition/Enigmata/Harmony. Для анализа по архетипам нужен
        представительный набор: по одному прогону из каждой серии
        Run01–Run18, тип инициализации чередуется.
        """
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
        """Итерация по run_id для тяжёлых запросов agent_relations."""
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
                print(f"     [{label}] run {i+1} ошибка: {e}", flush=True)
        print(f"     [{label}] done, {len(results)} runs OK       ", flush=True)
        return pd.concat(results, ignore_index=True) if results else pd.DataFrame()

    # ══════════════════════════════════════════════════════════
    #  01 — БАЗОВЫЕ МЕТРИКИ ВЗАИМОДЕЙСТВИЙ
    # ══════════════════════════════════════════════════════════

    def b01_basic_interactions(self) -> str:
        print("[01/09] Базовые метрики взаимодействий…", flush=True)
        rep = h2("1. Базовые метрики взаимодействий")

        df = self.q("""
            SELECT sr.scenario_name, sr.run_name,
                   count() AS total
            FROM interactions i
            JOIN simulation_runs sr ON i.run_id = sr.run_id
            GROUP BY sr.scenario_name, sr.run_name
            ORDER BY sr.scenario_name
        """)
        df = df.merge(self.runs_df[["scenario_name","init_type","group"]], on="scenario_name", how="left")

        # 1a — бар-чарт по сценариям
        fig, ax = plt.subplots(figsize=(16, 5))
        colors = [C3[INIT_TYPES.index(t)] if t in INIT_TYPES else "#999" for t in df["init_type"]]
        ax.bar(df["scenario_name"], df["total"]/1e6, color=colors, edgecolor="white", lw=.5)
        ax.set_title("Суммарное число взаимодействий по сценариям", fontsize=13, fontweight="bold")
        ax.set_ylabel("Контактов (млн)"); ax.set_xlabel("Сценарий")
        ax.tick_params(axis="x", rotation=75, labelsize=7)
        from matplotlib.patches import Patch
        ax.legend(handles=[Patch(facecolor=C3[i], label=t) for i, t in enumerate(INIT_TYPES)],
                  title="Инициализация")
        fig.tight_layout(); p1a = savefig(fig, "01a_total_by_scenario")

        # 1b — мин/среднее/макс по группам
        grp = df.groupby(["group","init_type"])["total"].agg(["mean","min","max"]).reset_index()
        fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=False)
        for ax, g in zip(axes, ["Гомогенные","Гетерогенные"]):
            sub = grp[grp["group"]==g]
            x = np.arange(len(sub))
            ax.bar(x-.25, sub["min"]/1e6,  .25, label="Мин",     color="#90CAF9")
            ax.bar(x,     sub["mean"]/1e6, .25, label="Среднее", color="#1565C0")
            ax.bar(x+.25, sub["max"]/1e6,  .25, label="Макс",    color="#0D47A1")
            ax.set_xticks(x); ax.set_xticklabels(sub["init_type"])
            ax.set_title(g); ax.set_ylabel("Контактов (млн)"); ax.legend()
        fig.suptitle("Мин/Среднее/Макс по группам", fontsize=12, fontweight="bold")
        fig.tight_layout(); p1b = savefig(fig, "01b_group_comparison")

        rep += img_md(p1a, "Суммарные контакты по сценариям")
        rep += img_md(p1b, "Мин/Среднее/Макс по группам")
        rep += "\n" + grp.to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════
    #  02 — ГЛУБОКИЙ АНАЛИЗ ОТКАЗОВ
    # ══════════════════════════════════════════════════════════

    def b02_refusals(self) -> str:
        print("[02/09] Анализ отказов…", flush=True)
        rep = h2("2. Глубокий анализ отказов")

        gl = self.q("""
            SELECT countIf(type=0)  AS refusals,
                   countIf(type=1)  AS successes,
                   countIf(type=-1) AS failures,
                   count()          AS total
            FROM interactions
        """)
        pct = float(gl["refusals"].iloc[0]) / float(gl["total"].iloc[0]) * 100
        rep += f"\n**Общий % отказов:** {pct:.2f}%\n\n" + gl.to_markdown(index=False) + "\n"

        # По локациям
        loc = self.q("""
            SELECT
                multiIf(slot_id IN (1,3,5,7), 'CLASS', slot_id IN (2,4,6), 'BREAK', 'GYM') AS location,
                countIf(type=0) AS refusals,
                count()         AS total,
                round(countIf(type=0)/count()*100,2) AS pct
            FROM interactions GROUP BY location ORDER BY pct DESC
        """)
        loc_ru = {"CLASS":"Занятия","BREAK":"Перемены","GYM":"Спортзал"}
        loc["label"] = loc["location"].map(loc_ru)
        fig, ax = plt.subplots(figsize=(7, 4))
        bars = ax.bar(loc["label"], loc["pct"], color=["#EF5350","#FF9800","#42A5F5"], edgecolor="white")
        for b, v in zip(bars, loc["pct"]):
            ax.text(b.get_x()+b.get_width()/2, b.get_height()+.15, f"{v:.1f}%", ha="center")
        ax.set_title("Процент отказов по локациям", fontsize=12, fontweight="bold")
        ax.set_ylabel("Доля отказов (%)"); fig.tight_layout(); p2a = savefig(fig, "02a_refusals_location")

        # Кривая Лоренца
        # ID агента уникален только внутри прогона: складывать to_id из
        # разных run_id нельзя, иначе один «агент» — это 54 человека.
        ag = self.q("""
            SELECT run_id, to_id AS agent_id, countIf(type=0) AS refusals
            FROM interactions GROUP BY run_id, to_id ORDER BY refusals
        """)
        vals = ag["refusals"].values.astype(float)
        n = len(vals)
        ly = np.cumsum(vals) / vals.sum()
        lx = np.arange(1, n+1) / n
        gini = 1 - 2*float(np.sum((ly[1:]+ly[:-1])*0.5*(lx[1:]-lx[:-1])))

        fig, ax = plt.subplots(figsize=(7, 6))
        ax.plot(lx*100, ly*100, color="#1565C0", lw=2, label="Кривая Лоренца")
        ax.plot([0,100],[0,100], "k--", lw=1, label="Равенство")
        ax.fill_between(lx*100, ly*100, lx*100, alpha=.12, color="#1565C0")
        ax.set_title(f"Концентрация отказов (Джини={gini:.3f})", fontsize=12, fontweight="bold")
        ax.set_xlabel("Доля агентов (%)"); ax.set_ylabel("Доля отказов (%)")
        ax.legend(); fig.tight_layout(); p2b = savefig(fig, "02b_lorenz")

        top10 = vals[int(n*.9):].sum() / vals.sum() * 100
        top50 = vals[int(n*.5):].sum() / vals.sum() * 100
        zero  = (ag["refusals"]==0).sum()

        # По архетипам
        arch = self.q("""
            SELECT ar.archetype,
                   countIf(i.type=0) AS refusals,
                   count()           AS total,
                   round(countIf(i.type=0)/count()*100,2) AS pct
            FROM interactions i
            JOIN agent_registry ar ON i.run_id=ar.run_id AND i.to_id=ar.agent_id
            GROUP BY ar.archetype ORDER BY pct DESC
        """)
        fig, ax = plt.subplots(figsize=(10, 5))
        colors_a = sns.color_palette("RdYlGn_r", len(arch))
        bars = ax.barh(arch["archetype"], arch["pct"], color=colors_a)
        for b, v in zip(bars, arch["pct"]):
            ax.text(b.get_width()+.1, b.get_y()+b.get_height()/2, f"{v:.1f}%", va="center", fontsize=9)
        ax.set_title("% отказов по архетипам", fontsize=12, fontweight="bold")
        ax.set_xlabel("Доля отказов (%)"); ax.invert_yaxis(); fig.tight_layout()
        p2c = savefig(fig, "02c_refusals_archetype")

        rep += h3("2a. По локациям"); rep += img_md(p2a, "Отказы по локациям")
        rep += h3("2b. Кривая Лоренца"); rep += img_md(p2b, "Концентрация отказов")
        rep += (f"\n- ТОП-10% = **{top10:.1f}%** всех отказов\n"
                f"- ТОП-50% = **{top50:.1f}%**\n"
                f"- Агентов без отказов: **{zero}** ({zero/n*100:.1f}%)\n"
                f"- Джини: **{gini:.3f}**\n")
        rep += h3("2c. По архетипам"); rep += img_md(p2c, "% отказов по архетипам")
        rep += "\n" + arch.to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════
    #  03 — РЕЛЯЦИОННЫЕ ПОРОГИ
    # ══════════════════════════════════════════════════════════

    def b03_relational_thresholds(self) -> str:
        print("[03/09] Реляционные пороги…", flush=True)
        rep = h2("3. Анализ реляционных порогов")

        # Per-run запросы (agent_relations слишком большая для full scan)
        days_str = "90,180,270,360,450,540,630,720,810,900,990,1080,1170"
        rows = []
        for _, rr in self.runs_df.iterrows():
            rid = rr["run_id"]; sn = rr["scenario_name"]
            print(f"     [B03] {sn}…", flush=True, end="\r")
            try:
                r = self.q(f"""
                    SELECT count() AS total,
                           sum(ar.utility >= 95 OR ar.trust >= 95 OR ar.affinity >= 95) AS soft,
                           sum((ar.utility >= 95 AND ar.trust >= 95)
                            OR (ar.utility >= 95 AND ar.affinity >= 95)
                            OR (ar.trust >= 95 AND ar.affinity >= 95)) AS hard
                    FROM agent_relations ar
                    JOIN interactions i
                        ON i.run_id = '{rid}' AND ar.day_id = i.day_id
                       AND ar.subject_id = i.from_id AND ar.object_id = i.to_id
                    WHERE ar.run_id = '{rid}' AND ar.day_id IN ({days_str}) AND ar.slot_id = 9
                """)
                if not r.empty:
                    rows.append({"scenario_name": sn, "total": int(r["total"].iloc[0] or 0),
                                 "soft": int(r["soft"].iloc[0] or 0), "hard": int(r["hard"].iloc[0] or 0)})
            except Exception as e:
                print(f"     [B03] {sn} ошибка: {e}", flush=True)
                rows.append({"scenario_name": sn, "total": 0, "soft": 0, "hard": 0})
        print(f"     [B03] done, {len(rows)} scenarios       ", flush=True)

        df = pd.DataFrame(rows)
        if df.empty or df["total"].sum() == 0:
            return rep + "\n*Нет данных.*\n"

        df["soft_pct"] = np.where(df["total"] > 0, df["soft"]/df["total"]*100, 0.0)
        df["hard_pct"] = np.where(df["total"] > 0, df["hard"]/df["total"]*100, 0.0)
        df = df.merge(self.runs_df[["scenario_name","init_type"]], on="scenario_name", how="left")

        fig, axes = plt.subplots(1, 2, figsize=(16, 5))
        from matplotlib.patches import Patch
        legend_h = [Patch(facecolor=C3[i], label=t) for i, t in enumerate(INIT_TYPES)]
        for ax, col, title in [
            (axes[0], "soft_pct", "Мягкое (≥95 хотя бы по одному)"),
            (axes[1], "hard_pct", "Строгое (≥95 по двум или трём)"),
        ]:
            clrs = [C3[INIT_TYPES.index(t)] if t in INIT_TYPES else "#999" for t in df["init_type"]]
            ax.bar(df["scenario_name"], df[col], color=clrs, edgecolor="white")
            ax.set_title(title, fontweight="bold"); ax.set_ylabel("% контактов")
            ax.tick_params(axis="x", rotation=75, labelsize=7)
            ax.legend(handles=legend_h, fontsize=8)
        fig.suptitle("Доля контактов при устойчивых связях (порог ≥95)", fontsize=12, fontweight="bold")
        fig.tight_layout(); p3 = savefig(fig, "03_relational_thresholds")

        rep += img_md(p3, "Реляционные пороги по сценариям")
        rep += "\n" + df[["scenario_name","init_type","soft_pct","hard_pct"]].to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════
    #  04 — СТАБИЛЬНЫЕ ПАРЫ
    # ══════════════════════════════════════════════════════════

    def b04_stable_pairs(self) -> str:
        print("[04/09] Стабильные пары…", flush=True)
        rep = h2("4. Стабильные пары")
        rep += ("\n**Логика:** Пара (A,B) неупорядочена: считаются все контакты "
                "между A и B за семестр. Доля пары — это `n_AB / N_A` или "
                "`n_AB / N_B`, где `N_A` — все контакты A (как инициатора и как "
                "адресата). Пара стабильна, если хотя бы у одного из партнёров "
                "доля ≥ порога.\n")

        thresholds = [0.90, 0.95, 0.995, 1.00]
        results = {f"{t*100:.1f}%": [] for t in thresholds}
        stats_rows = []

        for sem in range(1, N_SEMESTERS + 1):
            d1, d2 = SEM_RANGES[sem]
            print(f"     - Семестр {sem}/{N_SEMESTERS} (дни {d1}–{d2})", flush=True)

            df_s = self.q(f"""
                WITH
                pair_cnt AS (
                    SELECT run_id,
                           greatest(from_id, to_id) AS a,
                           least(from_id, to_id)    AS b,
                           count() AS n_ab
                    FROM interactions WHERE day_id BETWEEN {d1} AND {d2}
                    GROUP BY run_id, a, b
                ),
                agent_total AS (
                    SELECT run_id, agent_id, sum(cnt) AS n_a FROM (
                        SELECT run_id, from_id AS agent_id, count() AS cnt
                        FROM interactions WHERE day_id BETWEEN {d1} AND {d2}
                        GROUP BY run_id, from_id
                        UNION ALL
                        SELECT run_id, to_id AS agent_id, count() AS cnt
                        FROM interactions WHERE day_id BETWEEN {d1} AND {d2}
                        GROUP BY run_id, to_id
                    ) GROUP BY run_id, agent_id
                ),
                stability AS (
                    SELECT greatest(
                               p.n_ab / at_a.n_a,
                               p.n_ab / at_b.n_a
                           ) AS share
                    FROM pair_cnt p
                    JOIN agent_total at_a ON p.run_id=at_a.run_id AND p.a=at_a.agent_id
                    JOIN agent_total at_b ON p.run_id=at_b.run_id AND p.b=at_b.agent_id
                    WHERE at_a.n_a > 0 AND at_b.n_a > 0
                )
                SELECT
                    countIf(share >= 0.90)  AS cnt_90,
                    countIf(share >= 0.95)  AS cnt_95,
                    countIf(share >= 0.995) AS cnt_995,
                    countIf(share >= 1.00)  AS cnt_100,
                    count()                 AS total_pairs,
                    max(share)              AS max_share,
                    avg(share)              AS avg_share
                FROM stability
            """)

            if df_s.empty or df_s["total_pairs"].iloc[0] == 0:
                for t in thresholds:
                    results[f"{t*100:.1f}%"].append({"Семестр": sem, "Стаб.пар": 0})
                stats_rows.append({"Семестр": sem, "Макс. доля": 0.0, "Средняя доля": 0.0})
            else:
                nr = max(self.n_runs, 1)
                results["90.0%"].append({"Семестр": sem, "Стаб.пар": int(df_s["cnt_90"].iloc[0]) // nr})
                results["95.0%"].append({"Семестр": sem, "Стаб.пар": int(df_s["cnt_95"].iloc[0]) // nr})
                results["99.5%"].append({"Семестр": sem, "Стаб.пар": int(df_s["cnt_995"].iloc[0]) // nr})
                results["100.0%"].append({"Семестр": sem, "Стаб.пар": int(df_s["cnt_100"].iloc[0]) // nr})
                stats_rows.append({
                    "Семестр": sem,
                    "Макс. доля": round(float(df_s["max_share"].iloc[0]) * 100, 1),
                    "Средняя доля": round(float(df_s["avg_share"].iloc[0]) * 100, 2),
                })

        colors_t = ["#1565C0", "#2E7D32", "#E65100", "#6A1B9A"]
        fig, ax = plt.subplots(figsize=(11, 6))
        for (label, rows), c in zip(results.items(), colors_t):
            df_r = pd.DataFrame(rows)
            ax.plot(df_r["Семестр"], df_r["Стаб.пар"], marker="o", lw=2, color=c, label=f"Порог {label}")
        ax.set_title("Динамика стабильных пар по семестрам\n(среднее на университет)",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Семестр"); ax.set_ylabel("Стаб. пар / университет")
        ax.set_xticks(range(1, N_SEMESTERS+1))
        ax.legend(title="Порог"); ax.grid(True, alpha=.3)
        fig.tight_layout(); p4 = savefig(fig, "04_stable_pairs")

        rep += img_md(p4, "Динамика стабильных пар")
        for lbl, rows in results.items():
            rep += f"\n**Порог {lbl}:**\n" + pd.DataFrame(rows).to_markdown(index=False) + "\n"
        rep += ("\n**Наблюдённая концентрация пар.** Даже максимальная доля "
                "пары за семестр далека от 90%: контакты распределены по "
                "сотням партнёров.\n\n")
        rep += pd.DataFrame(stats_rows).to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════
    #  05 — ЭМОЦИОНАЛЬНЫЙ ФОН
    # ══════════════════════════════════════════════════════════

    def b05_emotions(self) -> str:
        print("[05/09] Эмоциональный фон…", flush=True)
        rep = h2("5. Эмоциональный фон коллектива")

        emo_sql = ", ".join([f"avg({e}) AS {e}_mean, stddevPop({e}) AS {e}_std" for e in EMOTION_AXES])
        df = self.q(f"SELECT day_id, {emo_sql} FROM agent_states GROUP BY day_id ORDER BY day_id")

        sem_starts = [sem_start(s) for s in range(1, N_SEMESTERS+1)]

        # 5a — временные ряды
        fig, axes = plt.subplots(4, 2, figsize=(16, 18), sharex=True)
        pal = sns.color_palette("tab10")
        for i, (col, lbl) in enumerate(EMOTION_RU.items()):
            ax = axes.flatten()[i]
            y = df[f"{col}_mean"]
            ylo, yhi = y - df[f"{col}_std"], y + df[f"{col}_std"]
            roll = y.rolling(14, center=True, min_periods=1).mean()
            ax.fill_between(df["day_id"], ylo, yhi, alpha=.12, color=pal[i])
            ax.plot(df["day_id"], y, color=pal[i], lw=.7, alpha=.6)
            ax.plot(df["day_id"], roll, color=pal[i], lw=2, label="MA-14")
            ax.axhline(0, color="grey", lw=.6, ls=":")
            for sd in sem_starts:
                ax.axvline(sd, color="red", lw=.6, ls="--", alpha=.5)
            ax.set_title(lbl, fontsize=10, fontweight="bold")
            ax.set_ylabel("Среднее ± std"); ax.legend(fontsize=8); ax.set_ylim(-35, 35)
        axes.flatten()[-1].set_visible(False)
        fig.suptitle("Динамика эмоционального фона — среднее по всем прогонам\n"
                     "Красные линии = начало семестра (полный сброс)", fontsize=12, fontweight="bold")
        fig.tight_layout(); p5a = savefig(fig, "05a_emotion_dynamics")

        # 5b — тепловая карта
        mean_cols = [f"{e}_mean" for e in EMOTION_AXES]
        df["bin"] = pd.cut(df["day_id"], bins=50, labels=False)
        hm = df.groupby("bin")[mean_cols].mean().T
        hm.index = [EMOTION_RU[e] for e in EMOTION_AXES]
        fig, ax = plt.subplots(figsize=(16, 5))
        sns.heatmap(hm, ax=ax, cmap="RdYlGn", center=0, vmin=-5, vmax=5,
                    linewidths=.2, cbar_kws={"label":"Среднее"})
        ax.set_title("Тепловая карта эмоций во времени", fontsize=12, fontweight="bold")
        ax.set_xlabel("Временной бин"); ax.set_ylabel("Ось")
        fig.tight_layout(); p5b = savefig(fig, "05b_emotion_heatmap")

        rep += img_md(p5a, "Эмоциональный фон: среднее ± std")
        rep += img_md(p5b, "Тепловая карта эмоций")
        return rep

    # ══════════════════════════════════════════════════════════
    #  06 — ВЫГОРАНИЕ ЛИДЕРА
    # ══════════════════════════════════════════════════════════

    def b06_leader_burnout(self) -> str:
        print("[06/09] Выгорание лидера…", flush=True)
        rep = h2("6. Эффект «Выгорания лидера»")

        # Per-run для agent_relations
        pop = self._iter_relations("""
            SELECT object_id AS agent_id,
                   countIf(trust>=80 AND affinity>=80) AS fans
            FROM agent_relations
            WHERE run_id = '{rid}' AND day_id IN (145,290,435,580,725,870,1015,1160)
            GROUP BY object_id ORDER BY fans DESC
        """, label="B06-pop")
        if pop.empty:
            return rep + "\n*Нет данных.*\n"
        emo_sql = ", ".join([f"avg({e}) AS {e}" for e in ["anger_humility","fear_calm","sadness_joy"]])
        emo = self.q(f"SELECT run_id, agent_id, {emo_sql} FROM agent_states GROUP BY run_id, agent_id")
        df = pop.merge(emo, on=["run_id","agent_id"], how="inner")

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        cols_burn = [("anger_humility","Гнев–Смирение"),("fear_calm","Страх–Спокойствие"),
                     ("sadness_joy","Печаль–Радость")]
        corrs = {}
        for ax, (col, lbl) in zip(axes, cols_burn):
            r, p = stats.pearsonr(df["fans"], df[col])
            corrs[lbl] = (r, p)
            ax.scatter(df["fans"], df[col], alpha=.25, s=8, color="#1565C0")
            z = np.polyfit(df["fans"], df[col], 1)
            xl = np.linspace(df["fans"].min(), df["fans"].max(), 100)
            ax.plot(xl, np.poly1d(z)(xl), "r-", lw=2)
            ax.set_title(f"{lbl}\nr={r:.3f}, p={p:.4f}", fontsize=10)
            ax.set_xlabel("Популярность"); ax.set_ylabel("Среднее")
        fig.suptitle("Выгорание лидера: популярность vs эмоции", fontsize=12, fontweight="bold")
        fig.tight_layout(); p6 = savefig(fig, "06_leader_burnout")

        rep += img_md(p6, "Выгорание лидера")
        for lbl, (r, pv) in corrs.items():
            sig = "✅ значимо" if pv < .05 else "❌ незначимо"
            rep += f"\n- **{lbl}**: r={r:.3f}, p={pv:.4f} ({sig})\n"
        return rep

    # ══════════════════════════════════════════════════════════
    #  07 — АТТРАКТОРНАЯ СХОДИМОСТЬ
    # ══════════════════════════════════════════════════════════

    def b07_attractor(self) -> str:
        print("[07/09] Аттракторная сходимость…", flush=True)
        rep = h2("7. Аттракторная сходимость сетей")

        matrices = {}
        for _, row in self.runs_df.iterrows():
            rid = row["run_id"]
            df_m = self.q(f"""
                SELECT ar1.archetype AS a_from, ar2.archetype AS a_to,
                       avg(rel.trust) AS avg_trust
                FROM (
                    SELECT subject_id, object_id, trust
                    FROM agent_relations
                    WHERE run_id = '{rid}' AND day_id >= {self.max_day - 2} AND slot_id = 9
                ) rel
                JOIN (SELECT agent_id, archetype FROM agent_registry WHERE run_id = '{rid}') ar1
                    ON rel.subject_id = ar1.agent_id
                JOIN (SELECT agent_id, archetype FROM agent_registry WHERE run_id = '{rid}') ar2
                    ON rel.object_id = ar2.agent_id
                GROUP BY a_from, a_to
            """)
            if not df_m.empty:
                matrices[row["scenario_name"]] = df_m.pivot_table(
                    index="a_from", columns="a_to", values="avg_trust", aggfunc="mean").fillna(0)

        recs = []
        for rname, scenarios in self.runs_df.groupby("run_name")["scenario_name"].apply(list).items():
            for i, s1 in enumerate(scenarios):
                for s2 in scenarios[i+1:]:
                    if s1 not in matrices or s2 not in matrices: continue
                    m1, m2 = matrices[s1], matrices[s2]
                    ri = m1.index.intersection(m2.index)
                    ci = m1.columns.intersection(m2.columns)
                    if len(ri) < 2 or len(ci) < 2: continue
                    v1 = m1.loc[ri,ci].values.flatten()
                    v2 = m2.loc[ri,ci].values.flatten()
                    if v1.std() < 1e-9 or v2.std() < 1e-9: continue
                    r, _ = stats.pearsonr(v1, v2)
                    recs.append({"run_name": rname, "s1": s1, "s2": s2, "pearson": r})

        if recs:
            df_s = pd.DataFrame(recs)
            fig, ax = plt.subplots(figsize=(10, 5))
            sns.boxplot(data=df_s, x="run_name", y="pearson", palette="Set2", ax=ax)
            ax.axhline(1.0, color="green", lw=1.5, ls="--", label="r=1")
            ax.axhline(0.5, color="orange", lw=1.5, ls=":", label="r=0.5")
            ax.set_title("Корреляция финальных Trust-матриц", fontsize=11, fontweight="bold")
            ax.set_xlabel("Серия"); ax.set_ylabel("r Пирсона")
            ax.tick_params(axis="x", rotation=45); ax.legend(); fig.tight_layout()
            p7 = savefig(fig, "07_attractor")
            rep += img_md(p7, "Аттракторная сходимость")
            rep += "\n" + df_s.describe().to_markdown() + "\n"
        else:
            rep += "\n*Недостаточно данных.*\n"
        return rep

    # ══════════════════════════════════════════════════════════
    #  08 — ЭМОЦИОНАЛЬНЫЕ ПУЗЫРИ
    # ══════════════════════════════════════════════════════════

    def b08_emotional_bubbles(self) -> str:
        print("[08/09] Эмоциональные пузыри…", flush=True)
        rep = h2("8. Эмоциональные пузыри (Emotional Contagion)")

        emo_sql = ", ".join([f"avg({e}) AS {e}" for e in EMOTION_AXES])

        # Per-run для agent_relations
        friends = self._iter_relations(f"""
            SELECT subject_id AS agent_id, object_id AS friend_id,
                   avg(affinity) AS aff
            FROM agent_relations
            WHERE run_id = '{{rid}}' AND day_id = {self.max_day}
            GROUP BY subject_id, object_id
            ORDER BY subject_id, aff DESC
        """, label="B08-friends", run_ids=self.sample_runs)

        if friends.empty:
            return rep + "\n*Нет данных.*\n"

        # Берём топ-3 друзей средствами pandas
        friends = friends.groupby(["run_id","agent_id"]).head(3)

        ego = self.q(f"SELECT run_id, agent_id, {emo_sql} FROM agent_states WHERE day_id={self.max_day} GROUP BY run_id, agent_id")

        # Эмоции друзей
        friend_cols = {e: f"f_{e}" for e in EMOTION_AXES}
        rename_map = {"agent_id": "friend_id"}
        rename_map.update(friend_cols)

        femo = friends.merge(ego.rename(columns=rename_map), on=["run_id","friend_id"], how="inner")
        femo_agg = femo.groupby(["run_id","agent_id"])[[f"f_{e}" for e in EMOTION_AXES]].mean().reset_index()
        df = ego.merge(femo_agg, on=["run_id","agent_id"], how="inner")

        assort = {}
        for e in EMOTION_AXES:
            sub = df[[e, f"f_{e}"]].dropna()
            if len(sub) < 10: continue
            r, p = stats.pearsonr(sub[e], sub[f"f_{e}"])
            assort[EMOTION_RU[e]] = {"r": r, "p": p, "sig": p < .05}

        df_a = pd.DataFrame(assort).T
        if df_a.empty or "sig" not in df_a.columns:
            return rep + "\n*Нет данных ассортативности.*\n"
            
        fig, ax = plt.subplots(figsize=(10, 5))
        clrs = ["#4CAF50" if bool(s) else "#EF5350" for s in df_a["sig"]]
        bars = ax.barh(df_a.index, df_a["r"], color=clrs, edgecolor="white")
        ax.axvline(0, color="black", lw=.8)
        for b, (_, row) in zip(bars, df_a.iterrows()):
            lbl = f"r={row['r']:.3f}" + (" *" if row["sig"] else "")
            ax.text(b.get_width()+.005*np.sign(b.get_width()),
                    b.get_y()+b.get_height()/2, lbl, va="center", fontsize=9)
        ax.set_title("Ассортативность: эго vs топ-3 друзей", fontsize=12, fontweight="bold")
        ax.set_xlabel("r Пирсона"); ax.invert_yaxis()
        from matplotlib.patches import Patch
        ax.legend(handles=[Patch(facecolor="#4CAF50",label="p<0.05"),
                           Patch(facecolor="#EF5350",label="p≥0.05")])
        fig.tight_layout(); p8 = savefig(fig, "08_emotional_bubbles")

        rep += img_md(p8, "Эмоциональная ассортативность")
        rep += "\n" + df_a.to_markdown() + "\n"
        return rep

    # ══════════════════════════════════════════════════════════
    #  09 — ПЕРИОД ПОЛУРАСПАДА ОТНОШЕНИЙ
    # ══════════════════════════════════════════════════════════

    def b09_halflife(self) -> str:
        print("[09/09] Период полураспада…", flush=True)
        rep = h2("9. Скорость полураспада отношений")

        df_list = []
        for i, rid in enumerate(self.sample_runs):
            print(f"     [B09-half] run {i+1}/{len(self.sample_runs)}…", flush=True, end="\r")
            try:
                sub = self.q(f"""
                    WITH bp AS (
                        SELECT greatest(from_id,to_id) AS a, least(from_id,to_id) AS b,
                               max(day_id) AS last_day
                        FROM interactions WHERE run_id = '{rid}'
                        GROUP BY a, b
                        HAVING last_day < {self.max_day - 200} AND last_day > 200
                    )
                    SELECT ar.archetype,
                           sum(rel.trust)    AS sum_trust,
                           sum(rel.affinity) AS sum_aff,
                           count()           AS n_pairs
                    FROM bp
                    JOIN agent_registry ar ON ar.run_id = '{rid}' AND bp.a = ar.agent_id
                    JOIN agent_relations rel ON rel.run_id = '{rid}'
                        AND rel.subject_id = bp.a AND rel.object_id = bp.b AND rel.day_id = bp.last_day
                    GROUP BY ar.archetype
                """)
                if not sub.empty:
                    df_list.append(sub)
            except Exception as e:
                print(f"     [B09-half] run {i+1} ошибка: {e}", flush=True)
        print(f"     [B09-half] done, {len(df_list)} runs OK       ", flush=True)

        if not df_list:
            return rep + "\n*Нет данных.*\n"

        merged = pd.concat(df_list, ignore_index=True)
        agg = merged.groupby("archetype").agg(
            sum_trust=("sum_trust","sum"), sum_aff=("sum_aff","sum"), n_pairs=("n_pairs","sum")
        ).reset_index()
        agg["trust_end"]    = agg["sum_trust"]  / agg["n_pairs"]
        agg["affinity_end"] = agg["sum_aff"] / agg["n_pairs"]
        agg = agg.sort_values("trust_end")

        fig, ax = plt.subplots(figsize=(10, 5))
        x = np.arange(len(agg))
        ax.bar(x-.2, agg["trust_end"],    .4, label="Trust",    color="#42A5F5")
        ax.bar(x+.2, agg["affinity_end"], .4, label="Affinity", color="#66BB6A")
        ax.set_xticks(x); ax.set_xticklabels(agg["archetype"], rotation=35, ha="right")
        ax.axhline(0, color="red", lw=1, ls="--"); ax.legend()
        ax.set_title("Trust/Affinity при последнем контакте по архетипам",
                     fontsize=12, fontweight="bold")
        ax.set_ylabel("Среднее значение"); fig.tight_layout()
        p9 = savefig(fig, "09_halflife_archetype")

        rep += img_md(p9, "Уровень отношений при «распаде» пары")
        rep += "\n" + agg[["archetype","trust_end","affinity_end","n_pairs"]].to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════
    #  ЗАПУСК
    # ══════════════════════════════════════════════════════════

    def run_all(self) -> None:
        print("\n" + "═" * 60)
        print("  БАЗОВАЯ АНАЛИТИКА — 9 блоков (01–09)")
        print("═" * 60 + "\n")

        analyses = [
            ("01", self.b01_basic_interactions),
            ("02", self.b02_refusals),
            ("03", self.b03_relational_thresholds),
            ("04", self.b04_stable_pairs),
            ("05", self.b05_emotions),
            ("06", self.b06_leader_burnout),
            ("07", self.b07_attractor),
            ("08", self.b08_emotional_bubbles),
            ("09", self.b09_halflife),
        ]

        for num, fn in analyses:
            try:
                section = fn()
                self._parts.append(section)
                print(f"  ✅ Блок {num} готов\n", flush=True)
            except Exception:
                err = traceback.format_exc()
                print(f"  ⚠️  Блок {num} — ошибка:\n{err}\n", flush=True)
                self._parts.append(f"\n\n## Блок {num} — ошибка\n\n```\n{err}\n```\n")

        self._save_report()

    def _save_report(self) -> None:
        header = textwrap.dedent(f"""
            # Отчёт: Базовая аналитика (блоки 01–09)

            **Дата:** {self._ts}
            **БД:** ClickHouse ({os.getenv('CLICKHOUSE_HOST', 'db.georgytadjiev.ink')})
            **Сценариев:** {self.n_runs}
            **Архетипов:** {len(self.archetypes)}: {', '.join(self.archetypes)}

            ---
        """).strip()
        path = OUTPUT_DIR / "baseline_report.md"
        path.write_text(header + "\n" + "\n".join(self._parts), encoding="utf-8")
        print(f"\n📝  Отчёт: {path}")
        print(f"📊  Графики: {PLOTS_DIR.resolve()}")
        print("═" * 60 + "\n")


if __name__ == "__main__":
    Baseline9().run_all()
