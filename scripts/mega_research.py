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
SEMESTER_LEN = 171   # дней в семестре ≈ 1365/8
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
    return (sem - 1) * SEMESTER_LEN + 1, sem * SEMESTER_LEN


# ══════════════════════════════════════════════════════════════════
#  ГЛАВНЫЙ КЛАСС
# ══════════════════════════════════════════════════════════════════

class MegaResearch:

    def __init__(self, host="localhost", port=8123,
                 username="default", password="clickhouse_pass"):
        print("🔌  Подключение к ClickHouse…", flush=True)
        self.db = clickhouse_connect.get_client(
            host=host, port=port, username=username, password=password
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
            for t in INIT_TYPES:
                if n.upper().endswith(t): return t
            return "OTHER"
        def _group(n):
            num = int(n.split("_")[0].replace("Run",""))
            return "Гомогенные" if num <= 7 else "Гетерогенные"
        df["init_type"] = df["scenario_name"].apply(_init)
        df["group"]     = df["run_name"].apply(_group)
        return df

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
        df = df.merge(meta[["scenario_name","init_type","group"]], on="scenario_name", how="left")

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

        days_str = "90, 180, 270, 360, 450, 540, 630, 720, 810, 900, 990, 1080, 1170, 1260, 1350"
        rows = []
        for idx, row in meta.iterrows():
            run_id = row["run_id"]
            scenario_name = row["scenario_name"]
            print(f"[Progress]     - Обработка сценария {idx + 1}/{len(meta)}: {scenario_name}", flush=True)
            query = f"""
            SELECT
                count() AS total,
                sum(ar.utility >= 75 OR ar.trust >= 75 OR ar.affinity >= 75) AS soft,
                sum((ar.utility >= 75 AND ar.trust >= 75) OR (ar.utility >= 75 AND ar.affinity >= 75) OR (ar.trust >= 75 AND ar.affinity >= 75)) AS hard
            FROM interactions i
            JOIN agent_relations ar
              ON i.run_id = ar.run_id
             AND i.day_id = ar.day_id
             AND ar.slot_id = 9
             AND i.from_id = ar.subject_id
             AND i.to_id = ar.object_id
            WHERE i.run_id = '{run_id}'
              AND i.day_id IN ({days_str})
              AND ar.run_id = '{run_id}'
              AND ar.day_id IN ({days_str})
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
        for ax, col, title in [(axes[0],"soft_pct","Мягкое (≥75 по одному)"),
                                (axes[1],"hard_pct","Строгое (≥75 по двум)")]:
            clrs = [C3[INIT_TYPES.index(t)] if t in INIT_TYPES else "#999" for t in df["init_type"]]
            ax.bar(df["scenario_name"], df[col], color=clrs, edgecolor="white")
            ax.set_title(title, fontweight="bold"); ax.set_ylabel("% контактов")
            ax.tick_params(axis="x", rotation=75, labelsize=7)
        from matplotlib.patches import Patch
        axes[1].legend(handles=[Patch(facecolor=C3[i],label=t) for i,t in enumerate(INIT_TYPES)],
                       title="Инициализация")
        fig.suptitle("Доля контактов при устойчивых связях (порог ≥75)", fontsize=12, fontweight="bold")
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
        rep += "\n**Описание:** Оценка распределения стабильности связей (по индексу Жаккара) по всем 42 университетам в динамике по семестрам.\n"

        bins = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        labels = ["0-10%", "10-20%", "20-30%", "30-40%", "40-50%", "50-60%", "60-70%", "70-80%", "80-90%", "90-100%"]
        
        semester_rows = []
        for sem in range(1, N_SEMESTERS+1):
            d1, d2 = sem_range(sem)
            print(f"[Progress]     - Обработка семестра {sem}/{N_SEMESTERS}", flush=True)
            df_s = self.q(f"""
                WITH
                pair_cnt AS (
                    SELECT run_id,
                           greatest(from_id,to_id) AS a,
                           least(from_id,to_id)    AS b,
                           count() AS pc
                    FROM interactions
                    WHERE day_id BETWEEN {d1} AND {d2}
                    GROUP BY run_id, a, b
                ),
                agent_total AS (
                    SELECT run_id, agent_id, sum(cnt) AS tc FROM (
                        SELECT run_id, from_id AS agent_id, count() AS cnt FROM interactions
                        WHERE day_id BETWEEN {d1} AND {d2} GROUP BY run_id, from_id
                        UNION ALL
                        SELECT run_id, to_id AS agent_id, count() AS cnt FROM interactions
                        WHERE day_id BETWEEN {d1} AND {d2} GROUP BY run_id, to_id
                    ) GROUP BY run_id, agent_id
                )
                SELECT
                    p.pc / at_a.tc AS jaccard
                FROM pair_cnt p
                JOIN agent_total at_a ON p.run_id = at_a.run_id AND p.a = at_a.agent_id
                UNION ALL
                SELECT
                    p.pc / at_b.tc AS jaccard
                FROM pair_cnt p
                JOIN agent_total at_b ON p.run_id = at_b.run_id AND p.b = at_b.agent_id
            """)
            
            row = {"Семестр": f"С{sem}"}
            # Инициализация нулями
            for lbl in labels:
                row[lbl] = 0.0
                
            if not df_s.empty:
                # Группируем по корзинам Жаккара
                binned = pd.cut(df_s["jaccard"], bins=bins, labels=labels, include_lowest=True)
                counts = binned.value_counts()
                for lbl in labels:
                    # Среднее число пар на один университет
                    row[lbl] = round(float(counts.get(lbl, 0)) / 42.0, 2)
            semester_rows.append(row)

        df_res = pd.DataFrame(semester_rows)

        # Построим красивый stacked bar chart
        fig, ax = plt.subplots(figsize=(12, 7))
        # Используем палитру для 10 категорий
        colors = sns.color_palette("Spectral_r", len(labels))
        
        bottom = np.zeros(len(df_res))
        for i, lbl in enumerate(labels):
            ax.bar(df_res["Семестр"], df_res[lbl], bottom=bottom, label=lbl, color=colors[i], edgecolor="white", width=0.6)
            bottom += df_res[lbl].values

        ax.set_title("Распределение стабильности пар по семестрам (в среднем на 1 университет)", fontsize=12, fontweight="bold")
        ax.set_xlabel("Семестр")
        ax.set_ylabel("Среднее количество пар")
        ax.legend(title="Интервал Жаккара (стабильность)", bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.grid(True, axis='y', alpha=.3)
        fig.tight_layout()
        p = savefig(fig, "04_stable_pairs")

        rep += img_md(p, "Динамика распределения стабильных пар по семестрам")
        rep += "\n### Распределение стабильных пар (среднее на один университет):\n"
        rep += df_res.to_markdown(index=False) + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 5 — ЭМОЦИОНАЛЬНЫЙ ФОН
    # ══════════════════════════════════════════════════════════════

    def b05_emotions(self) -> str:
        print("[Progress]  [05/18] Эмоциональный фон…", flush=True)
        rep = h2("5. Эмоциональный фон коллектива")

        emo_sql = ", ".join([f"avg({e}) AS {e}" for e in EMOTION_AXES])
        df = self.q(f"""
            SELECT day_id, {emo_sql}
            FROM agent_states
            GROUP BY day_id ORDER BY day_id
        """)

        # 5a — временные ряды
        fig, axes = plt.subplots(4, 2, figsize=(14, 16), sharex=True)
        for i, (col, lbl) in enumerate(EMOTION_RU.items()):
            ax = axes.flatten()[i]
            ax.plot(df["day_id"], df[col], color=sns.color_palette("tab10")[i], lw=.9, alpha=.7)
            roll = df[col].rolling(30, center=True).mean()
            ax.plot(df["day_id"], roll, "k--", lw=1.8, label="MA-30")
            ax.axhline(0, color="grey", lw=.7, ls=":"); ax.set_title(lbl, fontsize=10)
            ax.set_ylabel("Среднее"); ax.legend(fontsize=8)
        axes.flatten()[-1].set_visible(False)
        for ax in axes.flatten()[-2:]: ax.set_xlabel("День симуляции")
        fig.suptitle("Динамика эмоционального фона (7 осей, 1365 дней)", fontsize=13, fontweight="bold")
        fig.tight_layout(); p5a = savefig(fig, "05a_emotion_dynamics")

        # 5b — тепловая карта
        df["bin"] = pd.cut(df["day_id"], bins=50, labels=False)
        hm = df.groupby("bin")[EMOTION_AXES].mean().T
        hm.index = [EMOTION_RU[e] for e in EMOTION_AXES]
        fig, ax = plt.subplots(figsize=(16, 5))
        sns.heatmap(hm, ax=ax, cmap="RdYlGn", center=0,
                    linewidths=.2, cbar_kws={"label":"Среднее"})
        ax.set_title("Тепловая карта эмоций во времени", fontsize=12, fontweight="bold")
        ax.set_xlabel("Временной бин (1–50)"); ax.set_ylabel("Эмоциональная ось")
        fig.tight_layout(); p5b = savefig(fig, "05b_emotion_heatmap")

        # Дрейф
        early = df[df["day_id"]<=200][EMOTION_AXES].mean()
        late  = df[df["day_id"]>=1165][EMOTION_AXES].mean()
        drift = (late - early).abs()

        rep += img_md(p5a, "Временные ряды эмоционального фона (7 осей)")
        rep += img_md(p5b, "Тепловая карта эмоций во времени")
        rep += h3("Дрейф начало→конец")
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
            WHERE day_id IN (145,290,435,580,725,870,1015,1160,1305)
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
                FROM agent_relations rel
                JOIN agent_registry ar1 ON rel.run_id=ar1.run_id AND rel.subject_id=ar1.agent_id
                JOIN agent_registry ar2 ON rel.run_id=ar2.run_id AND rel.object_id=ar2.agent_id
                WHERE rel.run_id='{rid}' AND rel.day_id>=1315
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
            WHERE day_id=1365
            GROUP BY run_id, subject_id, object_id
            QUALIFY row_number() OVER (PARTITION BY run_id, subject_id ORDER BY avg(affinity) DESC) <= 3
        """)
        emo_sql = ", ".join([f"avg({e}) AS {e}" for e in EMOTION_AXES])
        ego  = self.q(f"SELECT run_id, agent_id, {emo_sql} FROM agent_states WHERE day_id=1365 GROUP BY run_id, agent_id")

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
                    HAVING last_day<1165 AND last_day>200
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
        rep += "\n**Гипотеза:** Хронически депрессивные агенты восстанавливаются после воскресного δ-сдвига медленнее нейтральных.\n"

        # Воскресенья ≈ каждые 6 дней (6-дневная учебная неделя)
        # Классифицируем агентов по среднему уровню sadness_joy
        # Воскресенья ≈ каждые 6 дней (6-дневная учебная неделя)
        # Классифицируем агентов по среднему уровню sadness_joy
        agent_baseline = self.q(f"""
            SELECT run_id, agent_id, avg(sadness_joy) AS baseline_joy
            FROM agent_states
            WHERE day_id<=200
            GROUP BY run_id, agent_id
        """)
        # Динамика по воскресеньям (day_id % 6 == 0)
        emo_sql = ", ".join([f"avg({e}) AS {e}" for e in EMOTION_AXES])
        sundays = self.q(f"""
            SELECT day_id, {emo_sql}
            FROM agent_states
            WHERE day_id % 6 = 0
            GROUP BY day_id ORDER BY day_id
        """)

        # Восстановление: после воскресенья (day N) смотрим day N+1, N+2, N+3
        # Упрощённо: сравниваем среднее эмоций в воскресенье vs следующие 5 дней
        all_days = self.q(f"""
            SELECT day_id, {emo_sql}
            FROM agent_states
            GROUP BY day_id ORDER BY day_id
        """)
        all_days["is_sunday"] = all_days["day_id"] % 6 == 0
        all_days["week"]      = all_days["day_id"] // 6

        fig, axes = plt.subplots(2, 1, figsize=(14, 9))

        # График 1: общая динамика sadness_joy с отметками воскресений
        ax = axes[0]
        ax.plot(all_days["day_id"], all_days["sadness_joy"], color="#1565C0", lw=.8, alpha=.8)
        sun_days = all_days[all_days["is_sunday"]]
        ax.scatter(sun_days["day_id"], sun_days["sadness_joy"],
                   color="#E65100", s=6, zorder=5, label="Воскресенья")
        ax.set_title("Динамика Печаль–Радость с отметками воскресных сбросов",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("День"); ax.set_ylabel("Среднее sadness_joy")
        ax.legend()

        # График 2: распределение агентов по базовому уровню joy
        ax = axes[1]
        ax.hist(agent_baseline["baseline_joy"], bins=60,
                color="#1565C0", edgecolor="white", alpha=.8)
        q25 = agent_baseline["baseline_joy"].quantile(.25)
        q75 = agent_baseline["baseline_joy"].quantile(.75)
        ax.axvline(q25, color="red",   lw=1.5, ls="--", label=f"Q25={q25:.1f} (депрессивные)")
        ax.axvline(q75, color="green", lw=1.5, ls="--", label=f"Q75={q75:.1f} (счастливые)")
        ax.axvline(0,   color="grey",  lw=1,   ls=":")
        ax.set_title("Распределение базового уровня Радости агентов (первые 200 дней)",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("Базовый sadness_joy"); ax.set_ylabel("Число агентов"); ax.legend()
        fig.tight_layout(); p10 = savefig(fig, "10_sunday_reset")

        # Скорость восстановления: раздельно для депрессивных (<=q25) и счастливых (>=q75) по всем 42 университетам
        df_recovery = self.q(f"""
            WITH
            agent_baseline AS (
                SELECT run_id, agent_id, avg(sadness_joy) AS baseline_joy
                FROM agent_states
                WHERE day_id<=200
                GROUP BY run_id, agent_id
            )
            SELECT day_id,
                   avgIf(sadness_joy, baseline_joy <= {q25}) AS depressed_joy,
                   avgIf(sadness_joy, baseline_joy >= {q75}) AS happy_joy
            FROM agent_states s
            JOIN agent_baseline b ON s.run_id=b.run_id AND s.agent_id=b.agent_id
            WHERE s.day_id%6 IN (0,1,2,3,4,5)
            GROUP BY day_id ORDER BY day_id
            LIMIT 400
        """)

        if not df_recovery.empty:
            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(df_recovery["day_id"], df_recovery["depressed_joy"], color="#EF5350", lw=1.5, label="Депрессивные (Q25)")
            ax.plot(df_recovery["day_id"], df_recovery["happy_joy"], color="#4CAF50", lw=1.5, label="Счастливые (Q75)")
            for sd in sun_days["day_id"].values[:70]:
                ax.axvline(sd, color="orange", lw=.4, alpha=.5)
            ax.set_title("Восстановление после воскресного сброса: депрессивные vs счастливые (все университеты)",
                         fontsize=11, fontweight="bold")
            ax.set_xlabel("День симуляции"); ax.set_ylabel("Среднее sadness_joy")
            ax.legend(); fig.tight_layout(); p10b = savefig(fig, "10b_sunday_recovery")
            rep += img_md(p10, "Воскресные сбросы и базовый уровень радости")
            rep += img_md(p10b, "Восстановление: депрессивные vs счастливые агенты")
        else:
            rep += img_md(p10, "Воскресные сбросы и базовый уровень радости")
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
            sub["sem"] = (sub["day_id"]-1)//SEMESTER_LEN + 1
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
            sub["sem"] = (sub["day_id"]-1)//SEMESTER_LEN + 1
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
        rep += "\n**Гипотеза:** Реляционные функции восстанавливают эмоциональный паттерн предыдущего семестра в первые 20–30 дней нового. Т.е. отношения являются «памятью» системы.\n"

        recovery_data = []
        for sem in range(2, N_SEMESTERS+1):
            sem_start = (sem-1)*SEMESTER_LEN + 1   # первый день нового семестра
            sem_prev_end = sem_start - 1

            # Эмоции в последние 5 дней предыдущего семестра (до сброса)
            emo_before_sql = ", ".join([f"avg({e}) AS {e}_before" for e in EMOTION_AXES])
            df_before = self.q(f"""
                SELECT run_id, agent_id, {emo_before_sql}
                FROM agent_states
                WHERE day_id BETWEEN {sem_prev_end-4} AND {sem_prev_end}
                GROUP BY run_id, agent_id
            """)

            # Отношения в последний день предыдущего семестра
            rel_sql = "avg(trust) AS trust_prev, avg(affinity) AS affinity_prev, avg(utility) AS utility_prev"
            df_rel = self.q(f"""
                SELECT run_id, subject_id AS agent_id, {rel_sql}
                FROM agent_relations
                WHERE day_id={sem_prev_end}
                GROUP BY run_id, subject_id
            """)

            # Эмоции на 1-й, 7-й, 14-й, 30-й день нового семестра
            for offset in [1, 7, 14, 30]:
                target_day = sem_start + offset - 1
                emo_after_sql = ", ".join([f"avg({e}) AS {e}_after" for e in EMOTION_AXES])
                df_after = self.q(f"""
                    SELECT run_id, agent_id, {emo_after_sql}
                    FROM agent_states WHERE day_id={target_day} GROUP BY run_id, agent_id
                """)

                if df_before.empty or df_rel.empty or df_after.empty:
                    continue
                merged = df_before.merge(df_rel, on=["run_id", "agent_id"], how="inner").merge(df_after, on=["run_id", "agent_id"], how="inner")
                if merged.empty: continue

                # Корреляция: trust_prev → sadness_joy_after (и др. эмоции)
                for e in ["sadness_joy", "alienation_openness", "shame_confidence"]:
                    if f"{e}_after" not in merged.columns: continue
                    r, p = stats.pearsonr(merged["trust_prev"], merged[f"{e}_after"])
                    recovery_data.append({
                        "Семестр": sem, "День от начала": offset,
                        "Эмоция": EMOTION_RU[e],
                        "r(trust→emotion)": round(r, 3),
                        "p": round(p, 4),
                        "Значимо": p < .05
                    })

        if not recovery_data:
            return rep + "\n*Недостаточно данных.*\n"

        df_rec = pd.DataFrame(recovery_data)
        # Pivot: ось X = день от начала семестра, ось Y = r
        fig, ax = plt.subplots(figsize=(12, 5))
        for (emo, sem_), grp in df_rec.groupby(["Эмоция","Семестр"]):
            grp_s = grp.sort_values("День от начала")
            ax.plot(grp_s["День от начала"], grp_s["r(trust→emotion)"],
                    lw=1, alpha=.5, marker="o", ms=3)
        # Средняя линия по всем
        mean_rec = df_rec.groupby("День от начала")["r(trust→emotion)"].mean()
        ax.plot(mean_rec.index, mean_rec.values, "k-", lw=3, label="Среднее по всем")
        ax.axhline(0, color="grey", lw=.8, ls=":"); ax.axhline(.3, color="green", lw=1, ls="--",
                                                                label="r=0.3 (умеренная связь)")
        ax.set_title("Корреляция накопленного Trust с эмоциями в начале нового семестра",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("День от начала семестра (после сброса)"); ax.set_ylabel("r Пирсона")
        ax.legend(); fig.tight_layout(); p12 = savefig(fig, "12_semester_amnesia")
        rep += img_md(p12, "Семестровая амнезия: накопленные отношения как эмоциональная память")
        rep += "\n" + df_rec.groupby("День от начала")["r(trust→emotion)"].describe().to_markdown() + "\n"
        return rep

    # ══════════════════════════════════════════════════════════════
    #  БЛОК 13 — ЛОВУШКА ЛОГАРИФМА
    # ══════════════════════════════════════════════════════════════

    def b13_log_trap(self) -> str:
        print("[Progress]  [13/18] Ловушка логарифма…", flush=True)
        rep = h2("13. «Ловушка логарифма» — бимодальность у Аналитика и Инноватора")
        rep += "\n**Гипотеза:** Архетипы с log(U) в формуле приоритета (Аналитик, Инноватор) избегают агентов с U≈0, создавая бимодальную структуру связей.\n"

        runs = self.meta()["run_id"].tolist()
        df_list = []
        limit_per_run = 2000000 // len(runs) + 1000
        for rid in runs:
            sub_df = self.q(f"""
                SELECT ar.archetype,
                       rel.utility
                FROM interactions i
                JOIN agent_registry ar ON ar.run_id = '{rid}' AND i.from_id=ar.agent_id
                JOIN agent_relations rel
                    ON  rel.run_id = '{rid}'
                    AND i.day_id=rel.day_id
                    AND rel.slot_id=9
                    AND i.from_id=rel.subject_id AND i.to_id=rel.object_id
                WHERE i.run_id = '{rid}'
                  AND i.day_id % 3 = 0
                  AND rel.utility BETWEEN -100 AND 100
                LIMIT {limit_per_run}
            """)
            if not sub_df.empty:
                df_list.append(sub_df)
        if len(df_list) == 0:
            return rep + "\n*Нет данных.*\n"
        df = pd.concat(df_list, ignore_index=True).head(2000000)

        log_mask  = df["archetype"].str.upper().isin([a.upper() for a in LOG_ARCHETYPES])
        df_log    = df[log_mask]
        df_other  = df[~log_mask]

        fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=False)

        for ax, data, title in [
            (axes[0], df_log,   "Аналитик + Инноватор (log-формула)"),
            (axes[1], df_other, "Остальные архетипы"),
        ]:
            for arch in data["archetype"].unique():
                sub = data[data["archetype"]==arch]["utility"]
                ax.hist(sub, bins=50, alpha=.5, density=True, label=arch)
            ax.axvline(0, color="red", lw=1.5, ls="--", label="U=0")
            ax.set_title(title, fontsize=11, fontweight="bold")
            ax.set_xlabel("Utility при взаимодействии"); ax.set_ylabel("Плотность")
            ax.legend(fontsize=8, ncol=2)
        fig.suptitle("Распределение utility при контактах: log-архетипы vs остальные",
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

        # Trust между парами архетипов (финальный)
        df_trust = self.q(f"""
            SELECT ar1.archetype AS subj, ar2.archetype AS obj,
                   avg(rel.trust) AS avg_trust, avg(rel.affinity) AS avg_affinity
            FROM agent_relations rel
            JOIN agent_registry ar1 ON rel.run_id=ar1.run_id AND rel.subject_id=ar1.agent_id
            JOIN agent_registry ar2 ON rel.run_id=ar2.run_id AND rel.object_id=ar2.agent_id
            WHERE rel.day_id = 1365 AND (rel.trust != 0 OR rel.affinity != 0)
            GROUP BY subj, obj
        """)
        pivot_trust = df_trust.pivot_table(index="subj", columns="obj",
                                           values="avg_trust", aggfunc="mean").fillna(0)
        fig, ax = plt.subplots(figsize=(12, 9))
        sns.heatmap(pivot_trust, ax=ax, cmap="RdYlGn", center=0, annot=True, fmt=".1f",
                    linewidths=.5, cbar_kws={"label":"Средний Trust"})
        ax.set_title("Финальный Trust между архетипами (последние 50 дней)",
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
            WHERE rel.day_id = 1365 AND rel.trust>=70
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
            HAVING last_day<1165 AND last_day>200
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
            HAVING last_day>=1165
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
            **Объём данных:** 42 серии × 1365 дней — ~56 млрд строк отношений,
            90 млн состояний агентов, 147 млн взаимодействий.
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
    MegaResearch(
        host="localhost",
        port=8123,
        username="default",
        password="clickhouse_pass",
    ).run_all()
