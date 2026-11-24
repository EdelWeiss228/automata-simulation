"""
mega_research.py
════════════════
Мега-скрипт полного анализа многоагентной симуляции.
18 блоков: базовая аналитика + поиск скрытых закономерностей.

Запуск:
    pip install clickhouse-connect pandas matplotlib seaborn scipy numpy networkx scikit-learn
    python mega_research.py

Всё считается на стороне ClickHouse (SQL-агрегации).
В Python попадают только итоговые таблицы (тысячи строк, не миллиарды).
Результат: data/plots/*.png + data/plots/*.pdf + data/output/report.md
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

# ══════════════════════════════════════════════════════════════════
#  КОНФИГУРАЦИЯ
# ══════════════════════════════════════════════════════════════════

PLOTS_DIR  = Path("data/plots")
OUTPUT_DIR = Path("data/output")
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
INIT_TYPES  = ["EMPTY", "RANDOM", "MIXED"]
C3          = ["#2196F3", "#FF9800", "#4CAF50"]   # EMPTY / RANDOM / MIXED
SEMESTER_LEN = 152   # дней в семестре ≈ 1213/8
N_SEMESTERS  = 8

# Архетипы с нелинейным log() в формуле приоритета
LOG_ARCHETYPES = ["Erudition", "Trailblaze"]

# ══════════════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ══════════════════════════════════════════════════════════════════

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
def hr() -> str: return "\n---\n"

def sem_range(sem: int) -> Tuple[int, int]:
    ranges = {
        # day_id начинается с нуля: 0..1212 — 1213 дней.
        1: (0, 152),
        2: (153, 302),
        3: (303, 455),
        4: (456, 605),
        5: (606, 758),
        6: (759, 908),
        7: (909, 1061),
        8: (1062, 1212)
    }
    return ranges.get(sem, (0, 1212))

def get_sem_from_day(day: int) -> int:
    if day <= 152: return 1
    if day <= 302: return 2
    if day <= 455: return 3
    if day <= 605: return 4
    if day <= 758: return 5
    if day <= 908: return 6
    if day <= 1061: return 7
    return 8

def sem_start_day(sem: int) -> int:
    starts = {1: 0, 2: 153, 3: 303, 4: 456, 5: 606, 6: 759, 7: 909, 8: 1062}
    return starts.get(sem, 1062)



# ══════════════════════════════════════════════════════════════════
#  ГЛАВНЫЙ КЛАСС
# ══════════════════════════════════════════════════════════════════

class MegaResearch:

    def __init__(self, host=None, port=None, username=None, password=None):
        from dotenv import load_dotenv
        load_dotenv()
        host = host or os.getenv("CLICKHOUSE_HOST", "localhost")
        port = int(port or os.getenv("CLICKHOUSE_PORT", "8123"))
        username = username or os.getenv("CLICKHOUSE_USER", "default")
        password = password or os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass")
        secure = os.getenv("CLICKHOUSE_SECURE", "False").lower() in ("true", "1", "yes")

        print("🔌  Подключение к ClickHouse…", flush=True)
        self.db = clickhouse_connect.get_client(
            host=host, port=port, username=username, password=password, secure=secure,
            autogenerate_session_id=False, connect_timeout=600, send_receive_timeout=600
        )
        self._parts: List[str] = []
        self._ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("✅  Соединение установлено.\n", flush=True)
        # Найдём репрезентативный run_id для детального анализа (предпочтительно MIXED с максимальным разнообразием архетипов)
        best_run_df = self.q("""
            SELECT r.run_id
            FROM simulation_runs r
            JOIN agent_registry a ON r.run_id = a.run_id
            WHERE r.scenario_name LIKE '%MIXED%'
            GROUP BY r.run_id
            ORDER BY count(DISTINCT a.archetype) DESC
            LIMIT 1
        """)
        if not best_run_df.empty:
            self.rep_run_id = best_run_df["run_id"].iloc[0]
        else:
            best_run_df = self.q("""
                SELECT r.run_id
                FROM simulation_runs r
                JOIN agent_registry a ON r.run_id = a.run_id
                GROUP BY r.run_id
                ORDER BY count(DISTINCT a.archetype) DESC
                LIMIT 1
            """)
            if not best_run_df.empty:
                self.rep_run_id = best_run_df["run_id"].iloc[0]
            else:
                mixed_runs = self.meta()
                self.rep_run_id = mixed_runs["run_id"].iloc[0]
        
        # Get max day dynamically from DB
        try:
            self.max_day = int(self.q("SELECT max(day_id) FROM agent_states").iloc[0, 0])
        except Exception:
            self.max_day = 1212
        try:
            self.n_runs = max(1, int(self.s("SELECT count() FROM simulation_runs")))
        except Exception:
            self.n_runs = 1

    # ── Запросы ──────────────────────────────────────────────────

    def q(self, sql: str) -> pd.DataFrame:
        return self.db.query_df(sql)

    def s(self, sql: str):
        df = self.db.query_df(sql)
        return df.iloc[0, 0]

    # ── Метаданные ───────────────────────────────────────────────

    def meta(self) -> pd.DataFrame:
        df = self.q("""
            SELECT run_id, scenario_name, run_name, start_time
            FROM simulation_runs ORDER BY scenario_name
        """)
        def _init(n):
            # Ищем суффикс через "_" — scenario_name вида RunXX_..._EMPTY|RANDOM|MIXED
            for t in INIT_TYPES:
                if ("_" + t) in n.upper(): return t
            return "OTHER"
        def _group(n):
            # Run15/Run16 — недостающие гомогенные архетипы.
            try:
                prefix = n.split("_")[0].replace("RUN", "Run")
                homogeneous = {f"Run{i:02d}" for i in range(1, 8)}
                homogeneous.update({"Run15", "Run16"})
                return "Гомогенные" if prefix in homogeneous else "Гетерогенные"
            except Exception:
                return "Неизвестно"
        def _nonlinear(n):
            u = n.upper()
            return "NL" in u or "NONLINEAR" in u or "NON_LINEAR" in u
        df["init_type"]  = df["scenario_name"].apply(_init)
        df["group"]      = df["run_name"].apply(_group)
        df["nonlinear"]  = df["scenario_name"].apply(_nonlinear)
        return df

    def _get_log_archetypes(self) -> list:
        """Динамически получить архетипы из БД и отобрать те, что содержат log в имени
        (Аналитик/Analyst и Инноватор/Innovator по диплому используют log(U)).
        Если не найдены по имени — берём первые два из списка."""
        archs = self.q("SELECT DISTINCT archetype FROM agent_registry ORDER BY archetype")
        if archs.empty:
            return []
        names = archs["archetype"].tolist()
        # Ключевые слова из диплома: аналитик, инноватор и их английские варианты
        keywords = ["аналит", "иннова", "analyst", "innovat", "erudition", "trailblaz"]
        log_archs = [a for a in names if any(k in a.lower() for k in keywords)]
        if not log_archs:
            # Фоллбэк: берём все имена — просто покажем все как одну группу
            log_archs = names[:2]
        return log_archs

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 1 — БАЗОВЫЕ МЕТРИКИ ВЗАИМОДЕЙСТВИЙ
    # ══════════════════════════════════════════════════════════════

    def b01_basic_interactions(self, meta: pd.DataFrame) -> str:
        print("[Progress]  [01/18] Базовые метрики взаимодействий…", flush=True)
        rep = h2("1. Базовые метрики взаимодействий")

        df = self.q("""
            SELECT sr.scenario_name,
                   sr.run_name,
                   count() AS total
            FROM interactions i
            JOIN simulation_runs sr ON i.run_id = sr.run_id
            GROUP BY sr.scenario_name, sr.run_name
            ORDER BY sr.scenario_name
        """)
        df = df.merge(meta[["scenario_name","init_type","group","nonlinear"]], on="scenario_name", how="left")

        # 1a — бар-чарт по сценариям
        fig, ax = plt.subplots(figsize=(16, 5))
        colors = [C3[INIT_TYPES.index(t)] if t in INIT_TYPES else "#999"
                  for t in df["init_type"]]
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
        rep += img_md(p1b, "Мин/Среднее/Макс по группам и типу инициализации")
        rep += "\n" + grp.to_markdown(index=False) + "\n"

        # 1c — нелинейность
        nl_grp = df.groupby("nonlinear")["total"].agg(["mean","std","count"]).reset_index()
        nl_grp["label"] = nl_grp["nonlinear"].map({True: "Нелинейные\n(NL)", False: "Линейные"})
        if len(nl_grp) >= 2:
            fig, ax = plt.subplots(figsize=(6, 5))
            ax.bar(nl_grp["label"], nl_grp["mean"]/1e6,
                   yerr=nl_grp["std"]/1e6, capsize=10,
                   color=["#EF5350","#42A5F5"], edgecolor="white", width=.5)
            for i, r in nl_grp.iterrows():
                ax.text(i, r["mean"]/1e6 + r["std"]/1e6 + 0.05,
                        f"n={int(r['count'])}", ha="center", fontsize=10)
            ax.set_title("Влияние нелинейности функций выбора\nна общую активность системы",
                         fontsize=12, fontweight="bold")
            ax.set_ylabel("Среднее число контактов (млн) ± std")
            fig.tight_layout(); p1c = savefig(fig, "01c_nonlinearity")
            rep += h3("1c. Нелинейность и активность")
            rep += img_md(p1c, "Нелинейные vs линейные сценарии: число контактов")
            # t-test
            nl_vals  = df[df["nonlinear"]==True]["total"].values
            lin_vals = df[df["nonlinear"]==False]["total"].values
            if len(nl_vals)>1 and len(lin_vals)>1:
                t, p_val = stats.ttest_ind(nl_vals, lin_vals)
                rep += (f"\n- t-критерий: t={t:.3f}, p={p_val:.4f}\n"
                        f"- {'✅ Нелинейность значимо влияет на активность' if p_val<.05 else '❌ Значимого влияния нет'}\n")
        else:
            rep += "\n*Нелинейных сценариев не обнаружено (в именах нет NL/NONLINEAR).*\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 2 — ГЛУБОКИЙ АНАЛИЗ ОТКАЗОВ
    # ══════════════════════════════════════════════════════════════

    def b02_refusals(self) -> str:
        print("[Progress]  [02/18] Анализ отказов…", flush=True)
        rep = h2("2. Глубокий анализ отказов")

        # Глобальная статистика
        gl = self.q("""
            SELECT countIf(type=0)  AS refusals,
                   countIf(type=1)  AS successes,
                   countIf(type=-1) AS failures,
                   count()            AS total
            FROM interactions
        """)
        pct = float(gl["refusals"].iloc[0]) / float(gl["total"].iloc[0]) * 100
        rep += f"\n**Общий % отказов:** {pct:.2f}%\n\n" + gl.to_markdown(index=False) + "\n"

        # По локациям
        loc = self.q("""
            SELECT
                multiIf(
                    slot_id IN (1, 3, 5, 7), 'CLASS',
                    slot_id IN (2, 4, 6),    'BREAK',
                    'GYM'
                ) AS location,
                   countIf(type=0) AS refusals,
                   count()           AS total,
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
        ag = self.q("""
            SELECT to_id AS agent_id,
                   countIf(type=0) AS refusals
            FROM interactions GROUP BY to_id ORDER BY refusals
        """)
        vals = ag["refusals"].values.astype(float)
        n = len(vals)
        ly = np.cumsum(vals) / vals.sum()
        lx = np.arange(1, n+1) / n
        gini = 1 - 2*float(np.sum((ly[1:] + ly[:-1]) * 0.5 * (lx[1:] - lx[:-1])))

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
                   count()             AS total,
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
        rep += (f"\n- ТОП-10% «мизантропов» = **{top10:.1f}%** всех отказов\n"
                f"- ТОП-50% = **{top50:.1f}%**\n"
                f"- Агентов без единого отказа: **{zero}** ({zero/n*100:.1f}%)\n"
                f"- Джини: **{gini:.3f}**\n")
        rep += h3("2c. По архетипам"); rep += img_md(p2c, "% отказов по архетипам")
        rep += "\n" + arch.to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 3 — РЕЛЯЦИОННЫЕ ПОРОГИ
    # ══════════════════════════════════════════════════════════════

    def b03_relational_thresholds(self, meta: pd.DataFrame) -> str:
        print("[Progress]  [03/18] Реляционные пороги…", flush=True)
        rep = h2("3. Анализ реляционных порогов")

        days_str = "90, 180, 270, 360, 450, 540, 630, 720, 810, 900, 990, 1080, 1170"
        rows = []
        for idx, row in meta.iterrows():
            run_id = row["run_id"]
            scenario_name = row["scenario_name"]
            print(f"[Progress]     - Обработка сценария {idx + 1}/{len(meta)}: {scenario_name}", flush=True)
            query = f"""
            SELECT
                count() AS total,
                sum(ar.utility >= 95 OR ar.trust >= 95 OR ar.affinity >= 95) AS soft,
                sum((ar.utility >= 95 AND ar.trust >= 95) OR (ar.utility >= 95 AND ar.affinity >= 95) OR (ar.trust >= 95 AND ar.affinity >= 95)) AS hard
            FROM (
                SELECT day_id, subject_id, object_id, utility, trust, affinity
                FROM agent_relations
                WHERE run_id = '{run_id}' AND day_id IN ({days_str}) AND slot_id = 9
            ) ar
            JOIN (
                SELECT day_id, from_id, to_id
                FROM interactions
                WHERE run_id = '{run_id}' AND day_id IN ({days_str})
            ) i
              ON i.day_id = ar.day_id
             AND i.from_id = ar.subject_id
             AND i.to_id = ar.object_id
            """
            df_r = self.q(query)
            if df_r.empty:
                rows.append({"scenario_name": scenario_name, "total": 0, "soft": 0, "hard": 0})
            else:
                rows.append({
                    "scenario_name": scenario_name,
                    "total": int(df_r["total"].iloc[0] or 0),
                    "soft": int(df_r["soft"].iloc[0] or 0),
                    "hard": int(df_r["hard"].iloc[0] or 0)
                })
        df = pd.DataFrame(rows)
        df["soft_pct"] = np.where(df["total"] > 0, df["soft"] / df["total"] * 100, 0.0)
        df["hard_pct"] = np.where(df["total"] > 0, df["hard"] / df["total"] * 100, 0.0)
        df = df.merge(meta[["scenario_name","init_type"]], on="scenario_name", how="left")

        fig, axes = plt.subplots(1, 2, figsize=(16, 5))
        from matplotlib.patches import Patch
        legend_handles = [Patch(facecolor=C3[i], label=t) for i, t in enumerate(INIT_TYPES)]
        legend_handles.append(Patch(facecolor="#999", label="OTHER"))
        for ax, col, title in [(axes[0], "soft_pct", "Мягкое (≥95 хотя бы по одному параметру)"),
                                (axes[1], "hard_pct", "Строгое (≥95 по двум или трём параметрам)")]:
            clrs = [C3[INIT_TYPES.index(t)] if t in INIT_TYPES else "#999" for t in df["init_type"]]
            bars = ax.bar(df["scenario_name"], df[col], color=clrs, edgecolor="white")
            ax.set_title(title, fontweight="bold"); ax.set_ylabel("% контактов")
            ax.tick_params(axis="x", rotation=75, labelsize=7)
            ax.legend(handles=legend_handles, title="Инициализация", fontsize=8)
        fig.suptitle("Доля контактов при устойчивых реляционных связях (порог ≥95)", fontsize=12, fontweight="bold")
        fig.tight_layout(); p = savefig(fig, "03_relational_thresholds")

        rep += img_md(p, "Реляционные пороги по сценариям")
        rep += "\n" + df[["scenario_name","init_type","soft_pct","hard_pct"]].to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 4 — СТАБИЛЬНЫЕ ПАРЫ
    # ══════════════════════════════════════════════════════════════

    def b04_stable_pairs(self) -> str:
        print("[Progress]  [04/18] Стабильные пары…", flush=True)
        rep = h2("4. Стабильные пары")
        rep += ("\n**Логика:** Для упорядоченной пары (A→B) вычисляется доля контактов агента A "
                "с агентом B от всех контактов A за семестр: `n_AB / N_A`. "
                "Пара считается стабильной, если эта доля ≥ порогу.\n")

        thresholds = [0.90, 0.95, 0.995, 1.00]
        results = {f"{t*100:.1f}%": [] for t in thresholds}

        for sem in range(1, N_SEMESTERS + 1):
            d1, d2 = sem_range(sem)
            print(f"[Progress]     - Семестр {sem}/{N_SEMESTERS} (дни {d1}–{d2})", flush=True)

            # n_AB — число контактов пары (направленно: from_id=A, to_id=B)
            # N_A  — все контакты агента A как инициатора + как адресата
            df_s = self.q(f"""
                WITH
                pair_cnt AS (
                    SELECT run_id,
                           from_id AS a,
                           to_id   AS b,
                           count() AS n_ab
                    FROM interactions
                    WHERE day_id BETWEEN {d1} AND {d2}
                    GROUP BY run_id, from_id, to_id
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
                    SELECT p.run_id,
                           p.a,
                           p.b,
                           p.n_ab,
                           at.n_a,
                           p.n_ab / at.n_a AS share
                    FROM pair_cnt p
                    JOIN agent_total at ON p.run_id=at.run_id AND p.a=at.agent_id
                    WHERE at.n_a > 0
                )
                SELECT
                    countIf(share >= 0.90)  AS cnt_90,
                    countIf(share >= 0.95)  AS cnt_95,
                    countIf(share >= 0.995) AS cnt_995,
                    countIf(share >= 1.00)  AS cnt_100,
                    count()                 AS total_pairs
                FROM stability
            """)

            if df_s.empty or df_s["total_pairs"].iloc[0] == 0:
                for t in thresholds:
                    results[f"{t*100:.1f}%"].append({"Семестр": sem, "Стаб.пар": 0})
            else:
                n_runs = max(1, self.n_runs)  # нормируем на число университетов
                results["90.0%"].append({"Семестр": sem, "Стаб.пар": int(df_s["cnt_90"].iloc[0]) // n_runs})
                results["95.0%"].append({"Семестр": sem, "Стаб.пар": int(df_s["cnt_95"].iloc[0]) // n_runs})
                results["99.5%"].append({"Семестр": sem, "Стаб.пар": int(df_s["cnt_995"].iloc[0]) // n_runs})
                results["100.0%"].append({"Семестр": sem, "Стаб.пар": int(df_s["cnt_100"].iloc[0]) // n_runs})

        colors_t = ["#1565C0", "#2E7D32", "#E65100", "#6A1B9A"]
        fig, ax = plt.subplots(figsize=(11, 6))
        for (label, rows), c in zip(results.items(), colors_t):
            df_r = pd.DataFrame(rows)
            ax.plot(df_r["Семестр"], df_r["Стаб.пар"],
                    marker="o", lw=2, color=c, label=f"Порог {label}")
        ax.set_title("Динамика стабильных пар по семестрам\n(среднее на один университет, метрика n_AB/N_A)",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Семестр"); ax.set_ylabel("Среднее число стабильных пар / университет")
        ax.set_xticks(range(1, N_SEMESTERS + 1))
        ax.set_xticklabels([f"С{i}" for i in range(1, N_SEMESTERS + 1)])
        ax.legend(title="Порог стабильности"); ax.grid(True, alpha=.3)
        fig.tight_layout(); p = savefig(fig, "04_stable_pairs")

        rep += img_md(p, "Динамика стабильных пар по семестрам (n_AB/N_A)")
        for lbl, rows in results.items():
            rep += f"\n**Порог {lbl}:**\n" + pd.DataFrame(rows).to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 5 — ЭМОЦИОНАЛЬНЫЙ ФОН
    # ══════════════════════════════════════════════════════════════

    def b05_emotions(self) -> str:
        print("[Progress]  [05/18] Эмоциональный фон…", flush=True)
        rep = h2("5. Эмоциональный фон коллектива")

        # Усредняем по всем прогонам — иначе среднее по 1620 агентов ≈ 0 из-за рандомной инициализации
        emo_avg_sql = ", ".join([f"avg({e}) AS {e}_mean, stddevPop({e}) AS {e}_std" for e in EMOTION_AXES])
        df = self.q(f"""
            SELECT day_id, {emo_avg_sql}
            FROM agent_states
            GROUP BY day_id ORDER BY day_id
        """)

        # Дни начала семестров для вертикальных маркеров
        sem_starts = [sem_start_day(s) for s in range(1, N_SEMESTERS + 1)]

        # 5a — временные ряды со стандартным отклонением
        fig, axes = plt.subplots(4, 2, figsize=(16, 18), sharex=True)
        pal = sns.color_palette("tab10")
        for i, (col, lbl) in enumerate(EMOTION_RU.items()):
            ax = axes.flatten()[i]
            mean_col = f"{col}_mean"
            std_col  = f"{col}_std"
            y    = df[mean_col]
            ylo  = y - df[std_col]
            yhi  = y + df[std_col]
            roll = y.rolling(14, center=True, min_periods=1).mean()

            ax.fill_between(df["day_id"], ylo, yhi, alpha=.12, color=pal[i])
            ax.plot(df["day_id"], y,    color=pal[i], lw=.7, alpha=.6)
            ax.plot(df["day_id"], roll, color=pal[i], lw=2,  label="MA-14")
            ax.axhline(0, color="grey", lw=.6, ls=":")
            # Семестровые границы — вертикальные пунктиры
            for sd in sem_starts:
                ax.axvline(sd, color="red", lw=.6, ls="--", alpha=.5)
            ax.set_title(lbl, fontsize=10, fontweight="bold")
            ax.set_ylabel("Среднее ± std"); ax.legend(fontsize=8)
            ax.set_ylim(-35, 35)
        axes.flatten()[-1].set_visible(False)
        for ax in [axes.flatten()[-2]]: ax.set_xlabel("День симуляции")
        # Аннотация: красные линии = начало семестра (сброс эмоций)
        fig.suptitle(
            f"Динамика эмоционального фона — среднее по всем {self.n_runs} прогонам\n"
            f"Красные линии = начало семестра (полный сброс эмоций до случайных [-30,30])",
            fontsize=12, fontweight="bold")
        fig.tight_layout(); p5a = savefig(fig, "05a_emotion_dynamics")

        # 5b — тепловая карта
        mean_cols = [f"{e}_mean" for e in EMOTION_AXES]
        df["bin"] = pd.cut(df["day_id"], bins=50, labels=False)
        hm = df.groupby("bin")[mean_cols].mean().T
        hm.index = [EMOTION_RU[e] for e in EMOTION_AXES]
        fig, ax = plt.subplots(figsize=(16, 5))
        sns.heatmap(hm, ax=ax, cmap="RdYlGn", center=0, vmin=-5, vmax=5,
                    linewidths=.2, cbar_kws={"label": "Среднее по всем прогонам"})
        ax.set_title(f"Тепловая карта эмоций во времени (усреднено по {self.n_runs} прогонам)",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Временной бин (1–50)"); ax.set_ylabel("Эмоциональная ось")
        fig.tight_layout(); p5b = savefig(fig, "05b_emotion_heatmap")

        # Дрейф
        early = df[df["day_id"] <= 100][[f"{e}_mean" for e in EMOTION_AXES]].mean()
        late  = df[df["day_id"] >= df["day_id"].max() - 100][[f"{e}_mean" for e in EMOTION_AXES]].mean()
        drift = (late - early).abs()
        drift.index = [e.replace("_mean","") for e in drift.index]

        rep += img_md(p5a, f"Эмоциональный фон: среднее ± std по всем {self.n_runs} прогонам")
        rep += img_md(p5b, "Тепловая карта эмоций во времени")
        rep += h3("Дрейф начало→конец")
        rep += ("\n*Примечание: из-за семестровых сбросов эмоций средние значения "
                "осциллируют. Дрейф = |avg(конец) − avg(начало)| без учёта сбросов.*\n")
        rep += "\n" + drift.rename(EMOTION_RU).to_frame("Δ дрейф").to_markdown() + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 6 — ВЫГОРАНИЕ ЛИДЕРА
    # ══════════════════════════════════════════════════════════════

    def b06_leader_burnout(self) -> str:
        print("[Progress]  [06/18] Выгорание лидера…", flush=True)
        rep = h2("6. Эффект «Выгорания лидера»")

        pop = self.q(f"""
            SELECT run_id, object_id AS agent_id,
                   countIf(trust>=80 AND affinity>=80) AS fans
            FROM agent_relations
            WHERE day_id IN (145,290,435,580,725,870,1015,1160,{self.max_day})
            GROUP BY run_id, object_id ORDER BY fans DESC
        """)
        emo_sql = ", ".join([f"avg({e}) AS {e}" for e in ["anger_humility","fear_calm","sadness_joy"]])
        emo = self.q(f"SELECT run_id, agent_id, {emo_sql} FROM agent_states GROUP BY run_id, agent_id")
        df  = pop.merge(emo, on=["run_id", "agent_id"], how="inner")

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        cols_burn = [("anger_humility","Гнев–Смирение"),
                     ("fear_calm",     "Страх–Спокойствие"),
                     ("sadness_joy",   "Печаль–Радость")]
        corrs = {}
        for ax, (col, lbl) in zip(axes, cols_burn):
            r, p = stats.pearsonr(df["fans"], df[col])
            corrs[lbl] = (r, p)
            ax.scatter(df["fans"], df[col], alpha=.25, s=8, color="#1565C0")
            z = np.polyfit(df["fans"], df[col], 1)
            xl = np.linspace(df["fans"].min(), df["fans"].max(), 100)
            ax.plot(xl, np.poly1d(z)(xl), "r-", lw=2)
            ax.set_title(f"{lbl}\nr={r:.3f}, p={p:.4f}", fontsize=10)
            ax.set_xlabel("Популярность (фанатов)"); ax.set_ylabel("Среднее значения оси")
        fig.suptitle("Выгорание лидера: корреляция популярности с негативными эмоциями",
                     fontsize=12, fontweight="bold")
        fig.tight_layout(); p6 = savefig(fig, "06_leader_burnout")

        rep += img_md(p6, "Корреляция популярности с эмоциями лидеров")
        for lbl, (r, pv) in corrs.items():
            sig = "✅ значимо" if pv < .05 else "❌ незначимо"
            rep += f"\n- **{lbl}**: r={r:.3f}, p={pv:.4f} ({sig})\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 7 — АТТРАКТОРНАЯ СХОДИМОСТЬ
    # ══════════════════════════════════════════════════════════════

    def b07_attractor(self, meta: pd.DataFrame) -> str:
        print("[Progress]  [07/18] Аттракторная сходимость…", flush=True)
        rep = h2("7. «Аттракторная сходимость» сетей")

        matrices = {}
        for _, row in meta.iterrows():
            rid = row["run_id"]
            df_m = self.q(f"""
                SELECT ar1.archetype AS a_from, ar2.archetype AS a_to,
                       avg(rel.trust) AS avg_trust
                FROM (
                    SELECT subject_id, object_id, trust
                    FROM agent_relations
                    WHERE run_id = '{rid}'
                      AND day_id >= {self.max_day - 2}
                      AND slot_id = 9
                ) rel
                JOIN (
                    SELECT agent_id, archetype
                    FROM agent_registry
                    WHERE run_id = '{rid}'
                ) ar1 ON rel.subject_id = ar1.agent_id
                JOIN (
                    SELECT agent_id, archetype
                    FROM agent_registry
                    WHERE run_id = '{rid}'
                ) ar2 ON rel.object_id = ar2.agent_id
                GROUP BY a_from, a_to
            """)
            if not df_m.empty:
                matrices[row["scenario_name"]] = df_m.pivot_table(
                    index="a_from", columns="a_to", values="avg_trust", aggfunc="mean").fillna(0)

        recs = []
        for rname, scenarios in meta.groupby("run_name")["scenario_name"].apply(list).items():
            for i, s1 in enumerate(scenarios):
                for s2 in scenarios[i+1:]:
                    if s1 not in matrices or s2 not in matrices: continue
                    m1, m2 = matrices[s1], matrices[s2]
                    ri = m1.index.intersection(m2.index)
                    ci = m1.columns.intersection(m2.columns)
                    if len(ri)<2 or len(ci)<2: continue
                    v1 = m1.loc[ri,ci].values.flatten()
                    v2 = m2.loc[ri,ci].values.flatten()
                    if v1.std()<1e-9 or v2.std()<1e-9: continue
                    r, _ = stats.pearsonr(v1, v2)
                    cos = float(np.dot(v1,v2)/(np.linalg.norm(v1)*np.linalg.norm(v2)+1e-9))
                    recs.append({"run_name":rname,"s1":s1,"s2":s2,"pearson":r,"cosine":cos})

        if recs:
            df_s = pd.DataFrame(recs)
            fig, ax = plt.subplots(figsize=(10, 5))
            sns.boxplot(data=df_s, x="run_name", y="pearson", palette="Set2", ax=ax)
            ax.axhline(1.0, color="green", lw=1.5, ls="--", label="Полная сходимость (r=1)")
            ax.axhline(0.5, color="orange", lw=1.5, ls=":", label="Умеренная (r=0.5)")
            ax.set_title("Корреляция финальных Trust-матриц (одни архетипы, разный старт)",
                         fontsize=11, fontweight="bold")
            ax.set_xlabel("Серия (Run)"); ax.set_ylabel("r Пирсона")
            ax.tick_params(axis="x", rotation=45); ax.legend(); fig.tight_layout()
            p7 = savefig(fig, "07_attractor")
            rep += img_md(p7, "Аттракторная сходимость: корреляция финальных матриц")
            rep += "\n" + df_s.describe().to_markdown() + "\n"
        else:
            rep += "\n*Недостаточно данных для сравнения.*\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 8 — ЭМОЦИОНАЛЬНЫЕ ПУЗЫРИ
    # ══════════════════════════════════════════════════════════════

    def b08_emotional_bubbles(self) -> str:
        print("[Progress]  [08/18] Эмоциональные пузыри…", flush=True)
        rep = h2("8. Эмоциональные пузыри (Emotional Contagion)")

        friends = self.q(f"""
            SELECT run_id, subject_id AS agent_id, object_id AS friend_id,
                   avg(affinity) AS aff
            FROM agent_relations
            WHERE day_id={self.max_day}
            GROUP BY run_id, subject_id, object_id
            QUALIFY row_number() OVER (PARTITION BY run_id, subject_id ORDER BY avg(affinity) DESC) <= 3
        """)
        emo_sql = ", ".join([f"avg({e}) AS {e}" for e in EMOTION_AXES])
        ego  = self.q(f"SELECT run_id, agent_id, {emo_sql} FROM agent_states WHERE day_id={self.max_day} GROUP BY run_id, agent_id")

        femo = friends.merge(
            ego.rename(columns={"agent_id":"friend_id"} |
                       {e:f"f_{e}" for e in EMOTION_AXES}),
            on=["run_id", "friend_id"], how="inner"
        ).groupby(["run_id", "agent_id"])[[f"f_{e}" for e in EMOTION_AXES]].mean().reset_index()
        df = ego.merge(femo, on=["run_id", "agent_id"], how="inner")

        assort = {}
        for e in EMOTION_AXES:
            sub = df[[e, f"f_{e}"]].dropna()
            if len(sub) < 10: continue
            r, p = stats.pearsonr(sub[e], sub[f"f_{e}"])
            assort[EMOTION_RU[e]] = {"r": r, "p": p, "sig": p < .05}

        df_a = pd.DataFrame(assort).T
        fig, ax = plt.subplots(figsize=(10, 5))
        clrs = ["#4CAF50" if s else "#EF5350" for s in df_a["sig"]]
        bars = ax.barh(df_a.index, df_a["r"], color=clrs, edgecolor="white")
        ax.axvline(0, color="black", lw=.8)
        for b, (_, row) in zip(bars, df_a.iterrows()):
            lbl = f"r={row['r']:.3f}" + (" *" if row["sig"] else "")
            ax.text(b.get_width()+.005*np.sign(b.get_width()),
                    b.get_y()+b.get_height()/2, lbl, va="center", fontsize=9)
        ax.set_title("Ассортативность по эмоциям: эго vs топ-3 друзей",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Коэффициент Пирсона"); ax.invert_yaxis()
        from matplotlib.patches import Patch
        ax.legend(handles=[Patch(facecolor="#4CAF50",label="p<0.05"),
                           Patch(facecolor="#EF5350",label="p≥0.05")])
        fig.tight_layout(); p8 = savefig(fig, "08_emotional_bubbles")
        rep += img_md(p8, "Эмоциональная ассортативность пар")
        rep += "\n" + df_a.to_markdown() + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 9 — ПЕРИОД ПОЛУРАСПАДА ОТНОШЕНИЙ
    # ══════════════════════════════════════════════════════════════

    def b09_halflife(self) -> str:
        print("[Progress]  [09/18] Период полураспада…", flush=True)
        rep = h2("9. Скорость полураспада отношений")

        # Получаем все run_id
        runs = self.meta()["run_id"].tolist()
        df_list = []
        for rid in runs:
            sub_df = self.q(f"""
                WITH bp AS (
                    SELECT greatest(from_id,to_id) AS a, least(from_id,to_id) AS b,
                           max(day_id) AS last_day
                    FROM interactions
                    WHERE run_id = '{rid}'
                    GROUP BY a, b
                    HAVING last_day<{self.max_day - 200} AND last_day>200
                )
                SELECT ar.archetype,
                       sum(rel.trust)    AS sum_trust,
                       sum(rel.affinity) AS sum_affinity,
                       count()           AS n_pairs
                FROM bp
                JOIN agent_registry ar ON ar.run_id = '{rid}' AND bp.a = ar.agent_id
                JOIN agent_relations rel ON rel.run_id = '{rid}'
                    AND rel.subject_id = bp.a AND rel.object_id = bp.b AND rel.day_id = bp.last_day
                GROUP BY ar.archetype
            """)
            if not sub_df.empty:
                df_list.append(sub_df)

        if len(df_list) == 0:
            return rep + "\n*Нет данных.*\n"

        merged_df = pd.concat(df_list, ignore_index=True)
        arch_decay = merged_df.groupby("archetype").agg(
            sum_trust=("sum_trust", "sum"),
            sum_affinity=("sum_affinity", "sum"),
            n_pairs=("n_pairs", "sum")
        ).reset_index()
        arch_decay["trust_at_end"] = arch_decay["sum_trust"] / arch_decay["n_pairs"]
        arch_decay["affinity_at_end"] = arch_decay["sum_affinity"] / arch_decay["n_pairs"]
        arch_decay = arch_decay.sort_values(by="trust_at_end")

        if not arch_decay.empty:
            fig, ax = plt.subplots(figsize=(10, 5))
            x = np.arange(len(arch_decay))
            ax.bar(x-.2, arch_decay["trust_at_end"],    .4, label="Trust",    color="#42A5F5")
            ax.bar(x+.2, arch_decay["affinity_at_end"], .4, label="Affinity", color="#66BB6A")
            ax.set_xticks(x); ax.set_xticklabels(arch_decay["archetype"], rotation=35, ha="right")
            ax.axhline(0, color="red", lw=1, ls="--"); ax.legend()
            ax.set_title("Trust/Affinity при последнем контакте по архетипам",
                         fontsize=12, fontweight="bold")
            ax.set_ylabel("Среднее значение параметра"); fig.tight_layout()
            p9 = savefig(fig, "09_halflife_archetype")
            rep += img_md(p9, "Уровень отношений при «распаде» пары")
            rep += "\n" + arch_decay.to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 10 — ЭФФЕКТ ВОСКРЕСНОГО СБРОСА
    # ══════════════════════════════════════════════════════════════

    def b10_sunday_reset(self) -> str:
        print("[Progress]  [10/18] Эффект воскресного сброса…", flush=True)
        rep = h2("10. «Эффект воскресного сброса»")
        rep += ("\n**Гипотеза:** Хронически депрессивные агенты восстанавливаются после воскресного "
                "δ-сдвига медленнее нейтральных.\n"
                "\n**Важно:** Базовый уровень эмоций считается ТОЛЬКО из первого семестра (до первого "
                "семестрового сброса), чтобы исключить влияние переинициализации на классификацию агентов.\n")

        import datetime as dt

        # Воскресенья — каждые 7 календарных дней в учебной неделе (6 дней/неделя).
        # В модели: 6-дневная рабочая неделя, воскресенье = каникулы, не входит в day_id.
        # «Воскресный сброс» происходит перед каждым понедельником, т.е. перед day_id кратным 6+1.
        # Реально day_id 1=Пн, 2=Вт, …, 6=Сб, 7=Пн (следующей недели) → воскресный сброс перед day 7,13,19...
        # Базовый уровень = первые 140 дней (не захватываем семестровый сброс ~154-й день)
        d1_s, d1_e = sem_range(1)
        safe_end = min(d1_e - 14, 140)  # не заходим в зону сброса

        agent_baseline = self.q(f"""
            SELECT run_id, agent_id, avg(sadness_joy) AS baseline_joy
            FROM agent_states
            WHERE day_id BETWEEN {d1_s} AND {safe_end}
            GROUP BY run_id, agent_id
        """)

        q25 = float(agent_baseline["baseline_joy"].quantile(.25))
        q75 = float(agent_baseline["baseline_joy"].quantile(.75))

        # График 1: общая динамика со скользящим окном и семестровыми границами
        emo_sql = ", ".join([f"avg({e}) AS {e}" for e in EMOTION_AXES])
        all_days = self.q(f"""
            SELECT day_id, {emo_sql} FROM agent_states GROUP BY day_id ORDER BY day_id
        """)
        sem_starts = [sem_start_day(s) for s in range(1, N_SEMESTERS + 1)]
        # Воскресенья в 6-дневной неделе: перед каждым 7-м, 13-м, 19-м... днём
        sunday_markers = [d for d in range(6, int(all_days["day_id"].max()), 6)]

        fig, axes = plt.subplots(2, 1, figsize=(16, 10))
        ax = axes[0]
        ax.plot(all_days["day_id"], all_days["sadness_joy"], color="#90CAF9", lw=.6, alpha=.7)
        roll = all_days["sadness_joy"].rolling(14, center=True, min_periods=1).mean()
        ax.plot(all_days["day_id"], roll, color="#1565C0", lw=2, label="MA-14")
        for sd in sunday_markers[:60]:   # только первые 360 дней — не загромождаем
            ax.axvline(sd, color="orange", lw=.3, alpha=.4)
        for ss in sem_starts:
            ax.axvline(ss, color="red", lw=1.2, ls="--", alpha=.8)
        ax.set_title("Динамика Печаль–Радость: синие MA-14, оранжевые = воскресенья, красные = начало семестра",
                     fontsize=11, fontweight="bold")
        ax.set_ylabel("Среднее sadness_joy по всем прогонам"); ax.legend(); ax.set_ylim(-35, 35)
        from matplotlib.lines import Line2D
        legend_els = [
            Line2D([0],[0], color="#1565C0", lw=2, label="MA-14 (среднее)"),
            Line2D([0],[0], color="orange", lw=1, ls="-", alpha=.6, label="Воскресный сброс (δ)"),
            Line2D([0],[0], color="red", lw=1.5, ls="--", label="Начало семестра (полный сброс)"),
        ]
        ax.legend(handles=legend_els, fontsize=9)

        ax = axes[1]
        ax.hist(agent_baseline["baseline_joy"], bins=60, color="#1565C0", edgecolor="white", alpha=.8)
        ax.axvline(q25, color="red",   lw=2, ls="--", label=f"Q25={q25:.1f}")
        ax.axvline(q75, color="green", lw=2, ls="--", label=f"Q75={q75:.1f}")
        ax.axvline(0,   color="grey",  lw=1, ls=":")
        ax.set_title(f"Базовый уровень Радости (первые {safe_end} дней — только 1-й семестр)",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("sadness_joy ([-30, 30])"); ax.set_ylabel("Число агентов-прогонов"); ax.legend()
        fig.tight_layout(); p10 = savefig(fig, "10_sunday_reset")

        # График 2: покадровое восстановление внутри каждой недели (только 1-й семестр, без сбросов)
        # Для каждой воскресной точки смотрим дни N-2, N-1, N, N+1, N+2, N+3, N+4 (неделя)
        # Только в пределах 1-го семестра (дни 1–140)
        weekly_sundays = [d for d in sunday_markers if d + 4 <= safe_end and d - 2 >= 1]

        if weekly_sundays and q25 != q75:
            df_rec = self.q(f"""
                WITH
                baseline AS (
                    SELECT run_id, agent_id, avg(sadness_joy) AS bj
                    FROM agent_states WHERE day_id BETWEEN {d1_s} AND {safe_end}
                    GROUP BY run_id, agent_id
                ),
                tagged AS (
                    SELECT s.run_id, s.agent_id, s.day_id, s.sadness_joy,
                           b.bj,
                           (s.day_id - 1) % 6 AS day_of_week   -- 0=Пн … 5=Сб
                    FROM agent_states s
                    JOIN baseline b ON s.run_id=b.run_id AND s.agent_id=b.agent_id
                    WHERE s.day_id BETWEEN 1 AND {safe_end}
                )
                SELECT day_of_week,
                       avgIf(sadness_joy, bj <= {q25}) AS dep_joy,
                       avgIf(sadness_joy, bj >= {q75}) AS hap_joy,
                       count() AS n
                FROM tagged
                GROUP BY day_of_week ORDER BY day_of_week
            """)

            if not df_rec.empty:
                day_labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
                fig, ax = plt.subplots(figsize=(9, 5))
                x = df_rec["day_of_week"].values
                ax.plot(x, df_rec["dep_joy"], "o-", color="#EF5350", lw=2, ms=7,
                        label=f"Депрессивные (baseline ≤ Q25={q25:.1f})")
                ax.plot(x, df_rec["hap_joy"], "s-", color="#4CAF50", lw=2, ms=7,
                        label=f"Счастливые (baseline ≥ Q75={q75:.1f})")
                ax.axhline(0, color="grey", lw=.8, ls=":")
                ax.set_xticks(range(6)); ax.set_xticklabels(day_labels)
                ax.set_title("Средний уровень sadness_joy по дням недели\n(1-й семестр, без семестровых сбросов)",
                             fontsize=11, fontweight="bold")
                ax.set_xlabel("День недели (Пн–Сб)"); ax.set_ylabel("Среднее sadness_joy")
                ax.legend(); ax.set_ylim(-35, 35); fig.tight_layout()
                p10b = savefig(fig, "10b_sunday_recovery")
                rep += img_md(p10, "Динамика с воскресными и семестровыми сбросами")
                rep += img_md(p10b, "Профиль sadness_joy по дням недели: депрессивные vs счастливые")
                rep += (f"\n- Q25 (депрессивные): baseline_joy ≤ {q25:.1f}\n"
                        f"- Q75 (счастливые): baseline_joy ≥ {q75:.1f}\n")
                return rep

        rep += img_md(p10, "Динамика с воскресными и семестровыми сбросами")
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 11 — ЗАКОН ПРОЩЕНИЯ (АСИММЕТРИЯ ЗАТУХАНИЯ)
    # ══════════════════════════════════════════════════════════════

    def b11_forgiveness_law(self) -> str:
        print("[Progress]  [11/18] Закон прощения…", flush=True)
        rep = h2("11. «Закон прощения» — асимметрия скорости затухания")
        rep += "\n**Гипотеза:** Положительные связи затухают с 0.5·d, отрицательные с d. Деструктор (d=1.0) забывает обиды быстрее, чем Протектор (d=0.2) забывает дружбу.\n"

        # Для каждого архетипа: средняя динамика позитивных и негативных trust по семестрам
        df = self.q(f"""
            SELECT ar.archetype,
                   rel.day_id,
                   avgIf(rel.trust, rel.trust>0)  AS avg_pos_trust,
                   avgIf(rel.trust, rel.trust<0)  AS avg_neg_trust,
                   avgIf(rel.affinity, rel.affinity>0) AS avg_pos_aff,
                   avgIf(rel.affinity, rel.affinity<0) AS avg_neg_aff,
                   count()                         AS n
            FROM agent_relations rel
            JOIN agent_registry ar ON rel.run_id=ar.run_id AND rel.subject_id=ar.agent_id
            WHERE rel.day_id % 30 = 0
            GROUP BY ar.archetype, rel.day_id
            ORDER BY ar.archetype, rel.day_id
        """)

        archetypes = df["archetype"].unique()
        palette_a  = sns.color_palette("tab10", len(archetypes))
        arch_color = dict(zip(archetypes, palette_a))

        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        for arch in archetypes:
            sub = df[df["archetype"]==arch].copy()
            sub["sem"] = sub["day_id"].apply(get_sem_from_day)
            agg = sub.groupby("sem")[["avg_pos_trust","avg_neg_trust"]].mean()
            axes[0].plot(agg.index, agg["avg_pos_trust"],
                         color=arch_color[arch], lw=1.5, marker="o", ms=4, label=arch)
            axes[1].plot(agg.index, agg["avg_neg_trust"].abs(),
                         color=arch_color[arch], lw=1.5, marker="o", ms=4, label=arch)

        for ax, title in [(axes[0],"Позитивный trust по семестрам"),
                          (axes[1],"|Негативный trust| по семестрам")]:
            ax.set_title(title, fontsize=11, fontweight="bold")
            ax.set_xlabel("Семестр"); ax.set_ylabel("Среднее значение trust")
            ax.set_xticks(range(1, N_SEMESTERS+1))
            ax.set_xticklabels([f"С{i}" for i in range(1, N_SEMESTERS+1)])
            ax.legend(fontsize=8, ncol=2)
        fig.suptitle("Закон прощения: позитивные vs негативные связи по архетипам",
                     fontsize=12, fontweight="bold")
        fig.tight_layout(); p11 = savefig(fig, "11_forgiveness_law")

        # Скорость изменения (slope) для каждого архетипа
        slopes = []
        for arch in archetypes:
            sub = df[df["archetype"]==arch].copy()
            sub["sem"] = sub["day_id"].apply(get_sem_from_day)
            agg = sub.groupby("sem")[["avg_pos_trust","avg_neg_trust"]].mean()
            if len(agg) < 3: continue
            slope_pos, *_ = stats.linregress(agg.index, agg["avg_pos_trust"])
            slope_neg, *_ = stats.linregress(agg.index, agg["avg_neg_trust"].abs())
            slopes.append({"Архетип":arch,
                           "Скорость угасания позитива":round(slope_pos,4),
                           "Скорость угасания негатива":round(slope_neg,4)})
        df_slopes = pd.DataFrame(slopes)

        rep += img_md(p11, "Асимметрия затухания: позитивные vs негативные связи")
        rep += "\n" + df_slopes.to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 12 — СЕМЕСТРОВАЯ АМНЕЗИЯ
    # ══════════════════════════════════════════════════════════════

    def b12_semester_amnesia(self) -> str:
        print("[Progress]  [12/18] Семестровая амнезия…", flush=True)
        rep = h2("12. «Семестровая амнезия» — что переживает переинициализацию эмоций?")
        rep += ("\n**Гипотеза:** После семестрового сброса эмоций агенты с высоким накопленным "
                "Trust быстрее восстанавливают свой эмоциональный ранг внутри коллектива. "
                "То есть отношения выступают «памятью», которая подтягивает эмоции назад.\n"
                "\n**Метрика:** Ранговая корреляция эмоционального ранга агента в последние дни "
                "старого семестра и его ранга в день 1, 7, 14, 30 нового семестра, "
                "для двух групп: высокий trust (топ-25%) vs низкий trust (нижние 25%).\n")

        rank_data = []
        for sem in range(2, N_SEMESTERS + 1):
            ss  = sem_start_day(sem)
            spe = ss - 1          # последний день предыдущего семестра

            # Средний trust агента в последние 5 дней семестра
            df_trust = self.q(f"""
                SELECT run_id, subject_id AS agent_id, avg(trust) AS avg_trust
                FROM agent_relations
                WHERE day_id BETWEEN {spe - 4} AND {spe}
                GROUP BY run_id, subject_id
            """)
            if df_trust.empty: continue

            # Ранг sadness_joy перед сбросом
            df_before = self.q(f"""
                SELECT run_id, agent_id, avg(sadness_joy) AS joy_before
                FROM agent_states WHERE day_id BETWEEN {spe - 4} AND {spe}
                GROUP BY run_id, agent_id
            """)
            if df_before.empty: continue

            # Ранг sadness_joy в разные дни после сброса
            for offset in [1, 7, 14, 30]:
                tday = ss + offset - 1
                df_after = self.q(f"""
                    SELECT run_id, agent_id, avg(sadness_joy) AS joy_after
                    FROM agent_states WHERE day_id = {tday}
                    GROUP BY run_id, agent_id
                """)
                if df_after.empty: continue

                merged = (df_trust
                          .merge(df_before, on=["run_id","agent_id"], how="inner")
                          .merge(df_after,  on=["run_id","agent_id"], how="inner"))
                if len(merged) < 30: continue

                # Ранги внутри каждого прогона
                merged["rank_before"] = merged.groupby("run_id")["joy_before"].rank()
                merged["rank_after"]  = merged.groupby("run_id")["joy_after"].rank()

                # Сплит по trust
                tq25 = merged["avg_trust"].quantile(.25)
                tq75 = merged["avg_trust"].quantile(.75)
                for grp_name, grp_mask in [("Высокий trust (Q75+)", merged["avg_trust"] >= tq75),
                                            ("Низкий trust (Q25-)",  merged["avg_trust"] <= tq25)]:
                    sub = merged[grp_mask]
                    if len(sub) < 10: continue
                    rho, p_val = stats.spearmanr(sub["rank_before"], sub["rank_after"])
                    rank_data.append({
                        "Семестр": sem,
                        "Дней после сброса": offset,
                        "Группа": grp_name,
                        "ρ Спирмена": round(rho, 3),
                        "p": round(p_val, 4),
                    })

        if not rank_data:
            return rep + "\n*Недостаточно данных.*\n"

        df_rank = pd.DataFrame(rank_data)
        fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
        colors_g = {"Высокий trust (Q75+)": "#4CAF50", "Низкий trust (Q25-)": "#EF5350"}
        for ax, offset in [(axes[0], 7), (axes[1], 30)]:
            sub = df_rank[df_rank["Дней после сброса"] == offset]
            for grp, gdf in sub.groupby("Группа"):
                ax.plot(gdf["Семестр"], gdf["ρ Спирмена"],
                        marker="o", lw=2, color=colors_g.get(grp, "#999"), label=grp)
            ax.axhline(0,   color="grey",  lw=.8, ls=":")
            ax.axhline(0.3, color="green", lw=1,  ls="--", label="ρ=0.3 (умеренная)")
            ax.set_title(f"День {offset} после семестрового сброса", fontsize=11, fontweight="bold")
            ax.set_xlabel("Семестр"); ax.set_ylabel("ρ Спирмена (ранг до → ранг после)")
            ax.set_xticks(range(2, N_SEMESTERS + 1))
            ax.legend(fontsize=8)
        fig.suptitle("Семестровая амнезия: восстанавливается ли эмоциональный ранг?\n"
                     "Сравнение агентов с высоким vs низким trust",
                     fontsize=12, fontweight="bold")
        fig.tight_layout(); p12 = savefig(fig, "12_semester_amnesia")

        rep += img_md(p12, "Ранговая корреляция эмоций до/после сброса: высокий vs низкий trust")
        rep += "\n" + df_rank.to_markdown(index=False) + "\n"
        rep += ("\n**Интерпретация:** Если ρ у «Высокий trust» > ρ у «Низкий trust» — "
                "накопленные отношения действительно служат эмоциональной памятью.\n")
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 13 — ЛОВУШКА ЛОГАРИФМА
    # ══════════════════════════════════════════════════════════════

    def b13_log_trap(self) -> str:
        print("[Progress]  [13/18] Ловушка логарифма…", flush=True)
        rep = h2("13. «Ловушка логарифма» — бимодальность у Аналитика и Инноватора")
        rep += ("\n**Гипотеза:** Архетипы с log(U) в формуле приоритета (Аналитик, Инноватор) "
                "избегают агентов с U≈0, создавая бимодальную структуру utility при контактах.\n")

        # Динамически определяем log-архетипы из БД
        log_archs = self._get_log_archetypes()
        if log_archs:
            rep += f"\n*Обнаруженные log-архетипы: {log_archs}*\n"
        else:
            rep += "\n*Log-архетипы не найдены по ключевым словам.*\n"

        runs = self.meta()["run_id"].tolist()
        df_list = []
        limit_per_run = max(50000, 2000000 // max(len(runs), 1))
        for rid in runs:
            sub_df = self.q(f"""
                SELECT ar.archetype,
                       rel.utility
                FROM interactions i
                JOIN agent_registry ar ON ar.run_id = '{rid}' AND i.from_id = ar.agent_id
                JOIN agent_relations rel
                    ON  rel.run_id    = '{rid}'
                    AND i.day_id      = rel.day_id
                    AND rel.slot_id   = 9
                    AND i.from_id     = rel.subject_id
                    AND i.to_id       = rel.object_id
                WHERE i.run_id = '{rid}'
                  AND i.day_id % 3 = 0
                  AND rel.utility BETWEEN -100 AND 100
                LIMIT {limit_per_run}
            """)
            if not sub_df.empty:
                df_list.append(sub_df)

        if not df_list:
            return rep + "\n*Нет данных (проверьте JOIN с agent_relations по slot_id=9).*\n"

        df = pd.concat(df_list, ignore_index=True).head(2_000_000)
        rep += f"\n*Всего строк для анализа: {len(df):,}*\n"

        if log_archs:
            log_mask = df["archetype"].str.lower().isin([a.lower() for a in log_archs])
        else:
            # Фоллбэк: сплит по медиане числа архетипов
            log_mask = pd.Series([False] * len(df), index=df.index)

        df_log   = df[log_mask]
        df_other = df[~log_mask]

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        for ax, data, title, desc in [
            (axes[0], df_log,   f"Log-архетипы: {log_archs}" if log_archs else "Log-архетипы (не найдены)",
             "log(U) в формуле приоритета — ожидается пустая зона у U=0"),
            (axes[1], df_other, "Остальные архетипы",
             "Линейные/sin/exp — ожидается равномерное или одномодальное распределение"),
        ]:
            if data.empty:
                ax.text(0.5, 0.5, "Нет данных", ha="center", va="center",
                        transform=ax.transAxes, fontsize=14, color="grey")
            else:
                for arch in data["archetype"].unique():
                    sub = data[data["archetype"] == arch]["utility"]
                    ax.hist(sub, bins=60, alpha=.45, density=True, label=arch)
            ax.axvline(0, color="red", lw=2, ls="--", label="U=0 (барьер для log)")
            ax.set_title(f"{title}\n({desc})", fontsize=10, fontweight="bold")
            ax.set_xlabel("Utility при взаимодействии [-100, 100]")
            ax.set_ylabel("Плотность вероятности")
            ax.legend(fontsize=8, ncol=2)
            # Аннотация: почему могут быть пики на ±100
            ax.text(0.02, 0.97,
                    "Пики у ±100 — saturate clip\nмодели (штатное поведение)",
                    transform=ax.transAxes, fontsize=7, va="top",
                    color="grey", style="italic")
        fig.suptitle("Распределение utility в момент взаимодействия: log-архетипы vs остальные",
                     fontsize=12, fontweight="bold")
        fig.tight_layout(); p13 = savefig(fig, "13_log_trap")

        # Bimodality coefficient (Sarle's)
        def bimod(x):
            n = len(x); sk = stats.skew(x); ku = stats.kurtosis(x)
            return (sk**2+1) / (ku + 3*(n-1)**2/((n-2)*(n-3)))

        bm_log   = bimod(df_log["utility"].dropna().values) if len(df_log)>10 else float("nan")
        bm_other = bimod(df_other["utility"].dropna().values) if len(df_other)>10 else float("nan")

        rep += img_md(p13, "Бимодальность utility у log-архетипов")
        rep += (f"\n- Коэф. бимодальности (log-архетипы): **{bm_log:.3f}**\n"
                f"- Коэф. бимодальности (остальные):     **{bm_other:.3f}**\n"
                f"- *Порог бимодальности: >0.555 (Sarle)*\n")
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 14 — НОНКОНФОРМИСТ × МЕДИАТОР
    # ══════════════════════════════════════════════════════════════

    def b14_nonconf_mediator(self) -> str:
        print("[Progress]  [14/18] Нонконформист × Медиатор…", flush=True)
        rep = h2("14. «Нонконформист × Медиатор» — взрывная асимметрия")
        rep += "\n**Гипотеза:** Нонконформист часто отказывает Медиатору, но Медиатор накапливает высокий trust через редкие успешные контакты.\n"

        df = self.q(f"""
            SELECT ar1.archetype AS arch_initiator,
                   ar2.archetype AS arch_target,
                   countIf(i.type=0)   AS refusals,
                   countIf(i.type=1)   AS successes,
                   countIf(i.type=-1)  AS failures,
                   count()               AS total,
                   round(countIf(i.type=0)/count()*100,2) AS refusal_pct
            FROM interactions i
            JOIN agent_registry ar1 ON i.run_id=ar1.run_id AND i.from_id=ar1.agent_id
            JOIN agent_registry ar2 ON i.run_id=ar2.run_id AND i.to_id=ar2.agent_id
            GROUP BY arch_initiator, arch_target
            ORDER BY refusal_pct DESC
        """)

        # Матрица отказов: архетип → архетип
        pivot = df.pivot_table(index="arch_initiator", columns="arch_target",
                               values="refusal_pct", aggfunc="mean").fillna(0)
        fig, ax = plt.subplots(figsize=(12, 9))
        sns.heatmap(pivot, ax=ax, cmap="Reds", annot=True, fmt=".1f",
                    linewidths=.5, cbar_kws={"label":"% отказов"})
        ax.set_title("Матрица отказов: архетип инициатора → архетип цели (%)",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Цель взаимодействия"); ax.set_ylabel("Инициатор")
        fig.tight_layout(); p14a = savefig(fig, "14a_archetype_refusal_matrix")

        # Trust между парами архетипов — берём диапазон последних 50 дней, не точный день
        max_rel_day = self.q("SELECT max(day_id) FROM agent_relations").iloc[0, 0]
        df_trust = self.q(f"""
            SELECT ar1.archetype AS subj, ar2.archetype AS obj,
                   avg(rel.trust)    AS avg_trust,
                   avg(rel.affinity) AS avg_affinity,
                   count()           AS n_pairs
            FROM agent_relations rel
            JOIN agent_registry ar1 ON rel.run_id=ar1.run_id AND rel.subject_id=ar1.agent_id
            JOIN agent_registry ar2 ON rel.run_id=ar2.run_id AND rel.object_id=ar2.agent_id
            WHERE rel.day_id >= {max_rel_day} - 50
            GROUP BY subj, obj
            HAVING count() >= 10
        """)
        pivot_trust = df_trust.pivot_table(index="subj", columns="obj",
                                           values="avg_trust", aggfunc="mean").fillna(0)
        fig, ax = plt.subplots(figsize=(12, 9))
        sns.heatmap(pivot_trust, ax=ax, cmap="RdYlGn", center=0, annot=True, fmt=".1f",
                    linewidths=.5, cbar_kws={"label":"Средний Trust"})
        ax.set_title(f"Финальный Trust между архетипами\n(последние 50 дней, day_id ≥ {max_rel_day}-50)",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Объект"); ax.set_ylabel("Субъект")
        fig.tight_layout(); p14b = savefig(fig, "14b_archetype_trust_matrix")

        rep += img_md(p14a, "Матрица отказов между архетипами")
        rep += img_md(p14b, "Матрица финального Trust между архетипами")
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 15 — ОППОРТУНИСТ В СПОРТЗАЛЕ
    # ══════════════════════════════════════════════════════════════

    def b15_gym_clustering(self) -> str:
        print("[Progress]  [15/18] Кластеризация в спортзале…", flush=True)
        rep = h2("15. «Оппортунист в спортзале» — кластеризация сети GYM")
        rep += "\n**Гипотеза:** Оппортунист (τ=3.0) создаёт случайную сеть в GYM, а Конкурент (ε=3.0 в GYM) — плотные кластеры.\n"

        try:
            import networkx as nx
        except ImportError:
            return rep + "\n*networkx не установлен. Запустите: pip install networkx*\n"

        # Граф взаимодействий в GYM по архетипам
        df_gym = self.q(f"""
            SELECT ar1.archetype AS arch1, ar2.archetype AS arch2,
                   i.run_id AS run_id,
                   greatest(i.from_id, i.to_id) AS a,
                   least(i.from_id, i.to_id)    AS b,
                   count() AS weight
            FROM interactions i
            JOIN agent_registry ar1 ON i.run_id=ar1.run_id AND i.from_id=ar1.agent_id
            JOIN agent_registry ar2 ON i.run_id=ar2.run_id AND i.to_id=ar2.agent_id
            WHERE i.slot_id = 8
            GROUP BY arch1, arch2, i.run_id, a, b
        """)

        if df_gym.empty:
            return rep + "\n*Нет данных по GYM.*\n"

        archetypes = df_gym["arch1"].unique()
        clust_results = []

        for arch in archetypes:
            sub = df_gym[(df_gym["arch1"]==arch) | (df_gym["arch2"]==arch)]
            run_coefficients = []
            for rid, group in sub.groupby("run_id"):
                G = nx.Graph()
                for _, row in group.iterrows():
                    G.add_edge(row["a"], row["b"], weight=row["weight"])
                if len(G.nodes) < 5: continue
                clust = nx.average_clustering(G)
                deg   = np.mean([d for _, d in G.degree()])
                run_coefficients.append((clust, deg, len(G.nodes)))
            if not run_coefficients: continue
            avg_clust = np.mean([x[0] for x in run_coefficients])
            avg_deg   = np.mean([x[1] for x in run_coefficients])
            avg_nodes = np.mean([x[2] for x in run_coefficients])
            clust_results.append({"Архетип":arch, "Кластеризация":round(avg_clust,4),
                                   "Средняя степень":round(avg_deg,2), "Вершин":int(avg_nodes)})

        df_clust = pd.DataFrame(clust_results).sort_values("Кластеризация", ascending=False)

        fig, ax = plt.subplots(figsize=(10, 5))
        colors_c = sns.color_palette("coolwarm_r", len(df_clust))
        bars = ax.bar(df_clust["Архетип"], df_clust["Кластеризация"],
                      color=colors_c, edgecolor="white")
        for b, v in zip(bars, df_clust["Кластеризация"]):
            ax.text(b.get_x()+b.get_width()/2, b.get_height()+.002, f"{v:.3f}",
                    ha="center", fontsize=9)
        ax.set_title("Коэффициент кластеризации сети GYM по архетипам",
                     fontsize=12, fontweight="bold")
        ax.set_ylabel("Коэф. кластеризации (0=случайная, 1=клика)")
        ax.tick_params(axis="x", rotation=35); fig.tight_layout()
        p15 = savefig(fig, "15_gym_clustering")

        rep += img_md(p15, "Кластеризация сети в спортзале по архетипам")
        rep += "\n" + df_clust.to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 16 — «ТЁПЛЫЕ ОСТРОВА»
    # ══════════════════════════════════════════════════════════════

    def b16_warm_islands(self) -> str:
        print("[Progress]  [16/18] Тёплые острова…", flush=True)
        rep = h2("16. «Тёплые острова» — закрытые кластеры Рефлектора и Протектора")
        rep += "\n**Гипотеза:** Рефлектор (d=0.1) и Протектор (d=0.2) создают устойчивые закрытые кластеры с trust≥70, исключающие другие архетипы.\n"

        try:
            import networkx as nx
        except ImportError:
            return rep + "\n*networkx не установлен.*\n"

        # Финальный граф trust≥70 с архетипами
        df_edges = self.q(f"""
            SELECT rel.run_id, rel.subject_id, rel.object_id,
                   avg(rel.trust) AS avg_trust,
                   ar.archetype
            FROM agent_relations rel
            JOIN agent_registry ar ON rel.run_id=ar.run_id AND rel.subject_id=ar.agent_id
            WHERE rel.day_id = {self.max_day} AND rel.trust>=70
            GROUP BY rel.run_id, rel.subject_id, rel.object_id, ar.archetype
        """)
        if df_edges.empty:
            return rep + "\n*Нет рёбер с trust≥70.*\n"

        # Получаем все пары agent_id -> archetype для точного маппинга
        df_registry = self.q("SELECT run_id, agent_id, archetype FROM agent_registry")
        registry_dict = {}
        for _, row in df_registry.iterrows():
            registry_dict[(row["run_id"], row["agent_id"])] = row["archetype"]

        components = []
        comp_stats = []
        for rid, group in df_edges.groupby("run_id"):
            G = nx.Graph()
            for _, row in group.iterrows():
                G.add_edge(row["subject_id"], row["object_id"], weight=row["avg_trust"])
            run_components = [c for c in nx.connected_components(G) if len(c) >= 3]
            components.extend(run_components)
            for comp in run_components:
                arch_counts = {}
                for node in comp:
                    a = registry_dict.get((rid, node), "UNKNOWN")
                    arch_counts[a] = arch_counts.get(a, 0) + 1
                dominant = max(arch_counts, key=arch_counts.get)
                dom_pct  = arch_counts[dominant] / len(comp) * 100
                comp_stats.append({
                    "run_id": rid,
                    "Размер кластера": len(comp),
                    "Доминирующий архетип": dominant,
                    "Доля доминанта (%)": round(dom_pct, 1),
                    "Все архетипы": str(arch_counts)
                })

        df_comp = pd.DataFrame(comp_stats)
        if not df_comp.empty:
            df_comp = df_comp.sort_values("Размер кластера", ascending=False).head(20)

        # Распределение размеров компонент
        sizes = [len(c) for c in components]
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        axes[0].hist(sizes, bins=30, color="#1565C0", edgecolor="white")
        axes[0].set_title("Распределение размеров «тёплых островов» (trust≥70)",
                          fontsize=11, fontweight="bold")
        axes[0].set_xlabel("Размер кластера"); axes[0].set_ylabel("Число кластеров")

        # Топ-архетипы в крупных кластерах
        if not df_comp.empty:
            dom_counts = df_comp["Доминирующий архетип"].value_counts()
            axes[1].bar(dom_counts.index, dom_counts.values,
                        color=sns.color_palette("Set2", len(dom_counts)), edgecolor="white")
            axes[1].set_title("Доминирующий архетип в кластерах", fontsize=11, fontweight="bold")
            axes[1].set_xlabel("Архетип"); axes[1].set_ylabel("Число кластеров")
            axes[1].tick_params(axis="x", rotation=35)
        fig.suptitle("Тёплые острова: кластеры с trust≥70", fontsize=12, fontweight="bold")
        fig.tight_layout(); p16 = savefig(fig, "16_warm_islands")

        rep += img_md(p16, "Тёплые острова: распределение и доминирующие архетипы")
        rep += f"\n**Всего кластеров (≥3 агентов): {len(components)}**\n\n"
        if not df_comp.empty:
            rep += df_comp.head(15).to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 17 — ДЕСТРУКТОР КАК КАТАЛИЗАТОР РАСПАДА
    # ══════════════════════════════════════════════════════════════

    def b17_destructor_catalyst(self) -> str:
        print("[Progress]  [17/18] Деструктор как катализатор…", flush=True)
        rep = h2("17. Деструктор как «катализатор» распада пар")
        rep += "\n**Гипотеза:** Пары (A, B) распадаются значимо чаще, если агент A получил много отказов от Деструкторов.\n"

        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            return rep + "\n*scikit-learn не установлен. Запустите: pip install scikit-learn*\n"

        # Распавшиеся пары
        df_broken = self.q(f"""
            SELECT run_id,
                   greatest(from_id,to_id) AS a,
                   least(from_id,to_id)    AS b,
                   max(day_id)               AS last_day,
                   1                         AS broken
            FROM interactions
            GROUP BY run_id,a,b
            HAVING last_day<{self.max_day - 200} AND last_day>200
            LIMIT 50000
        """)

        # Устойчивые пары (дожили до конца)
        df_stable = self.q(f"""
            SELECT run_id,
                   greatest(from_id,to_id) AS a,
                   least(from_id,to_id)    AS b,
                   max(day_id)               AS last_day,
                   0                         AS broken
            FROM interactions
            GROUP BY run_id,a,b
            HAVING last_day>={self.max_day - 200}
            LIMIT 50000
        """)

        df_all = pd.concat([df_broken, df_stable], ignore_index=True)

        # Число отказов от Деструкторов, которые получил агент A
        df_destr = self.q(f"""
            SELECT i.run_id, i.to_id AS agent_id,
                   countIf(i.type=0) AS destructor_refusals
            FROM interactions i
            JOIN agent_registry ar ON i.run_id=ar.run_id AND i.from_id=ar.agent_id
            WHERE ar.archetype ILIKE '%Nihility%'
            GROUP BY i.run_id, agent_id
        """)

        df_all = df_all.merge(df_destr.rename(columns={"agent_id":"a",
                                                        "destructor_refusals":"destr_ref_a"}),
                              on=["run_id", "a"], how="left").fillna(0)

        # Логистическая регрессия
        X = df_all[["destr_ref_a"]].values
        y = df_all["broken"].values
        scaler = StandardScaler(); X_sc = scaler.fit_transform(X)
        lr = LogisticRegression(max_iter=300).fit(X_sc, y)
        coef = float(lr.coef_[0][0])
        odds = np.exp(coef)

        # График: распределение отказов от Деструкторов у распавшихся vs устойчивых
        fig, ax = plt.subplots(figsize=(9, 5))
        for val, lbl, c in [(1,"Распавшиеся пары","#EF5350"),
                             (0,"Устойчивые пары","#4CAF50")]:
            sub = df_all[df_all["broken"]==val]["destr_ref_a"]
            ax.hist(sub, bins=40, alpha=.6, density=True, label=lbl, color=c)
        ax.set_title("Число отказов от Деструкторов: распавшиеся vs устойчивые пары",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("Отказов от Деструкторов (агент A)"); ax.set_ylabel("Плотность")
        ax.legend(); fig.tight_layout(); p17 = savefig(fig, "17_destructor_catalyst")

        rep += img_md(p17, "Деструктор как катализатор распада пар")
        rep += (f"\n- Коэф. логит-регрессии (стандартизованный): **{coef:.3f}**\n"
                f"- Odds Ratio: **{odds:.3f}**\n"
                f"- {'✅ Деструкторы действительно ускоряют распад' if odds>1.05 else '❌ Эффект незначим'}\n")
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 18 — ЭФФЕКТ ПЕРВОГО СЕМЕСТРА (PATH DEPENDENCY)
    # ══════════════════════════════════════════════════════════════

    def b18_first_semester(self, meta: pd.DataFrame) -> str:
        print("[Progress]  [18/18] Эффект первого семестра…", flush=True)
        rep = h2("18. «Эффект первого семестра» — path dependency")
        rep += "\n**Гипотеза:** Ранговая позиция агента по числу контактов в 1-м семестре является сильным предиктором его позиции в 8-м семестре (особенно в EMPTY-сценариях).\n"

        # Только EMPTY сценарии
        empty_ids = meta[meta["init_type"]=="EMPTY"]["run_id"].tolist()
        if not empty_ids:
            return rep + "\n*Нет EMPTY-сценариев.*\n"
        ids_str = ", ".join([f"'{r}'" for r in empty_ids])

        d1_s, d1_e = sem_range(1)
        d8_s, d8_e = sem_range(8)

        df_sem1 = self.q(f"""
            SELECT run_id, agent_id, sum(cnt) AS contacts_s1 FROM (
                SELECT run_id, from_id AS agent_id, count() AS cnt FROM interactions
                WHERE run_id IN ({ids_str}) AND day_id BETWEEN {d1_s} AND {d1_e}
                GROUP BY run_id, from_id
                UNION ALL
                SELECT run_id, to_id AS agent_id, count() AS cnt FROM interactions
                WHERE run_id IN ({ids_str}) AND day_id BETWEEN {d1_s} AND {d1_e}
                GROUP BY run_id, to_id
            ) GROUP BY run_id, agent_id
        """)
        df_sem8 = self.q(f"""
            SELECT run_id, agent_id, sum(cnt) AS contacts_s8 FROM (
                SELECT run_id, from_id AS agent_id, count() AS cnt FROM interactions
                WHERE run_id IN ({ids_str}) AND day_id BETWEEN {d8_s} AND {d8_e}
                GROUP BY run_id, from_id
                UNION ALL
                SELECT run_id, to_id AS agent_id, count() AS cnt FROM interactions
                WHERE run_id IN ({ids_str}) AND day_id BETWEEN {d8_s} AND {d8_e}
                GROUP BY run_id, to_id
            ) GROUP BY run_id, agent_id
        """)
        df = df_sem1.merge(df_sem8, on=["run_id", "agent_id"], how="inner").dropna()
        if len(df) < 10:
            return rep + "\n*Недостаточно данных.*\n"

        df["rank_s1"] = df.groupby("run_id")["contacts_s1"].rank(ascending=False)
        df["rank_s8"] = df.groupby("run_id")["contacts_s8"].rank(ascending=False)
        rho, p = stats.spearmanr(df["rank_s1"], df["rank_s8"])

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        # Scatter рангов
        ax = axes[0]
        ax.scatter(df["rank_s1"], df["rank_s8"], alpha=.2, s=8, color="#1565C0")
        z = np.polyfit(df["rank_s1"], df["rank_s8"], 1)
        xl = np.linspace(df["rank_s1"].min(), df["rank_s1"].max(), 100)
        ax.plot(xl, np.poly1d(z)(xl), "r-", lw=2)
        ax.set_title(f"Ранги: Семестр 1 vs Семестр 8\nρ Спирмена={rho:.3f}, p={p:.4f}",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("Ранг в Семестре 1"); ax.set_ylabel("Ранг в Семестре 8")

        # Топ-10% в С1 → как они выглядят в С8?
        top10_s1 = df[df["rank_s1"] <= df["rank_s1"].quantile(.1)]
        ax = axes[1]
        ax.hist(top10_s1["rank_s8"] / df["rank_s8"].max() * 100, bins=30,
                color="#E65100", edgecolor="white", alpha=.8)
        ax.axvline(10, color="green", lw=2, ls="--", label="ТОП-10% в С8")
        ax.set_title("Где оказываются ТОП-10% С1 в финальном рейтинге (С8)?",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("Перцентиль ранга в Семестре 8 (0=лучший)")
        ax.set_ylabel("Число агентов"); ax.legend(); fig.tight_layout()
        p18 = savefig(fig, "18_first_semester_path_dependency")

        rep += img_md(p18, "Эффект первого семестра: ранговая корреляция С1 → С8")
        rep += (f"\n- **ρ Спирмена:** {rho:.3f}\n"
                f"- **p-значение:** {p:.6f}\n"
                f"- {'✅ Сильная path dependency: первый семестр определяет судьбу' if rho>.5 else ('⚠️ Умеренная зависимость' if rho>.3 else '❌ Первый семестр не предсказывает финал')}\n")
        return rep

    # ══════════════════════════════════════════════════════════════
    #  ОТЧЁТ И ЗАПУСК
    # ══════════════════════════════════════════════════════════════

    def _save_report(self) -> None:
        header = textwrap.dedent(f"""
            # Мега-отчёт: Многоагентная симуляция социально-эмоциональных отношений

            **Дата генерации:** {self._ts}
            **База данных:** ClickHouse (localhost:8123)
            **Объём данных:** {self.n_runs} серий × 1213 дней; отношения
            пишутся только для ненулевых связей.
            **Блоков анализа:** 18 (9 базовых + 9 новых гипотез)

            ---
        """).strip()
        path = OUTPUT_DIR / "report.md"
        path.write_text(header + "\n" + "\n".join(self._parts), encoding="utf-8")
        print(f"\n📝  Отчёт сохранён → {path}")

    def run_all(self) -> None:
        print("\n" + "═"*62)
        print("  MEGA RESEARCH — 18 блоков анализа")
        print("═"*62 + "\n")

        import shutil
        import os
        plots_dir = "data/plots"
        if os.path.exists(plots_dir):
            try:
                shutil.rmtree(plots_dir)
            except Exception as e:
                print(f"Предупреждение при очистке {plots_dir}: {e}", flush=True)
        os.makedirs(plots_dir, exist_ok=True)

        meta = self.meta()
        print(f"  Сценариев в базе: {len(meta)}\n")

        analyses = [
            ("01", lambda: self.b01_basic_interactions(meta)),
            ("02", self.b02_refusals),
            ("03", lambda: self.b03_relational_thresholds(meta)),
            ("04", self.b04_stable_pairs),
            ("05", self.b05_emotions),
            ("06", self.b06_leader_burnout),
            ("07", lambda: self.b07_attractor(meta)),
            ("08", self.b08_emotional_bubbles),
            ("09", self.b09_halflife),
            ("10", self.b10_sunday_reset),
            ("11", self.b11_forgiveness_law),
            ("12", self.b12_semester_amnesia),
            ("13", self.b13_log_trap),
            ("14", self.b14_nonconf_mediator),
            ("15", self.b15_gym_clustering),
            ("16", self.b16_warm_islands),
            ("17", self.b17_destructor_catalyst),
            ("18", lambda: self.b18_first_semester(meta)),
        ]

        for num, fn in analyses:
            try:
                section = fn()
                self._parts.append(section)
                print(f"[Progress]     ✅ Блок {num} готов", flush=True)
            except Exception:
                err = traceback.format_exc()
                print(f"[Progress]     ⚠️  Блок {num} — ошибка:\n{err}", flush=True)
                self._parts.append(f"\n\n## Блок {num} — ошибка выполнения\n\n```\n{err}\n```\n")

        self._save_report()
        print(f"\n✅  Все блоки завершены.")
        print(f"    Графики: {PLOTS_DIR.resolve()}")
        print(f"    Отчёт:   {(OUTPUT_DIR/'report.md').resolve()}")
        print("═"*62 + "\n")


# ══════════════════════════════════════════════════════════════════
#  ТОЧКА ВХОДА
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    MegaResearch().run_all()
