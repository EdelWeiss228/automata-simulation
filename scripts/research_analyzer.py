"""
research_analyzer.py
====================
Профессиональный аналитический скрипт для обработки и визуализации результатов
долгосрочной многоагентной симуляции социально-эмоциональных отношений.

База данных: ClickHouse (локальный, 56+ млрд строк)
Автор: ResearchAnalyzer v1.0
"""

from __future__ import annotations

import os
import textwrap
import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional

import clickhouse_connect
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages
from scipy import stats

warnings.filterwarnings("ignore")
matplotlib.rcParams["font.family"] = "DejaVu Sans"

# ─────────────────────────────── КОНФИГУРАЦИЯ ────────────────────────────────

PLOTS_DIR = Path("data/plots")
OUTPUT_DIR = Path("data/output")
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = sns.color_palette("tab20", 20)
PALETTE_3 = ["#2196F3", "#FF9800", "#4CAF50"]  # EMPTY / RANDOM / MIXED

EMOTION_AXES = [
    "sadness_joy",
    "fear_calm",
    "anger_humility",
    "disgust_acceptance",
    "habit_surprise",
    "shame_confidence",
    "alienation_openness",
]
EMOTION_LABELS = {
    "sadness_joy": "Печаль–Радость",
    "fear_calm": "Страх–Спокойствие",
    "anger_humility": "Гнев–Смирение",
    "disgust_acceptance": "Отвращение–Принятие",
    "habit_surprise": "Привычка–Удивление",
    "shame_confidence": "Стыд–Уверенность",
    "alienation_openness": "Отчуждение–Открытость",
}

HOMOGENEOUS_RUNS = [f"Run{i:02d}" for i in range(1, 8)]   # Run01–Run07
HETEROGENEOUS_RUNS = [f"Run{i:02d}" for i in range(8, 15)]  # Run08–Run14

INIT_TYPES = ["EMPTY", "RANDOM", "MIXED"]

STABILITY_THRESHOLDS = [0.90, 0.95, 0.995, 1.00]

DPI_PNG = 200
DPI_PDF = 150

# ─────────────────────────────── ВСПОМОГАТЕЛЬНЫЕ УТИЛИТЫ ─────────────────────


def _savefig(fig: plt.Figure, name: str) -> str:
    """Сохраняет фигуру в PNG и PDF, возвращает путь к PNG."""
    png_path = PLOTS_DIR / f"{name}.png"
    pdf_path = PLOTS_DIR / f"{name}.pdf"
    fig.savefig(png_path, dpi=DPI_PNG, bbox_inches="tight")
    fig.savefig(pdf_path, dpi=DPI_PDF, bbox_inches="tight")
    plt.close(fig)
    return str(png_path)


def _section(title: str) -> str:
    return f"\n\n## {title}\n"


def _subsection(title: str) -> str:
    return f"\n### {title}\n"


def _img(path: str, caption: str = "") -> str:
    rel = os.path.relpath(path, OUTPUT_DIR)
    return f"\n![{caption}]({rel})\n*{caption}*\n"


# ─────────────────────────────── ОСНОВНОЙ КЛАСС ──────────────────────────────


class ResearchAnalyzer:
    """
    Главный класс анализатора симуляции.

    Порядок работы:
        analyzer = ResearchAnalyzer()
        analyzer.run_all()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        username: str = "default",
        password: str = "clickhouse_pass",
    ) -> None:
        print("🔌  Подключение к ClickHouse…")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = clickhouse_connect.get_client(
            host=host, port=port, username=username, password=password
        )
        self._report_parts: list[str] = []
        self._generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("✅  Подключение установлено.")

    # ──────────────────────────── УТИЛИТЫ ЗАПРОСОВ ───────────────────────────

    def _q(self, sql: str) -> pd.DataFrame:
        """Выполнить SQL и вернуть DataFrame."""
        return self.client.query_df(sql)

    def _scalar(self, sql: str):
        """Вернуть первое значение первой строки."""
        df = self._q(sql)
        return df.iloc[0, 0]

    # ──────────────────────────── ЗАГРУЗКА МЕТАДАННЫХ ────────────────────────

    def _load_runs_meta(self) -> pd.DataFrame:
        """Загрузить таблицу сценариев с классификацией."""
        df = self._q(
            """
            SELECT
                run_id,
                scenario_name,
                run_name,
                start_time
            FROM simulation_runs
            ORDER BY scenario_name
            """
        )
        # Определяем тип инициализации по суффиксу
        def _init_type(name: str) -> str:
            for t in INIT_TYPES:
                if name.upper().endswith(t):
                    return t
            return "UNKNOWN"

        def _group(name: str) -> str:
            # run_name вида RunXX_...
            prefix = name.split("_")[0]  # RunXX
            num = int(prefix.replace("Run", ""))
            return "homogeneous" if num <= 7 else "heterogeneous"

        def _nonlinear(name: str) -> bool:
            return "NONLINEAR" in name.upper() or "NL" in name.upper()

        df["init_type"] = df["scenario_name"].apply(_init_type)
        df["group"] = df["run_name"].apply(_group)
        df["nonlinear"] = df["scenario_name"].apply(_nonlinear)
        return df

    # ═════════════════════════════════════════════════════════════════════════
    #  ЧАСТЬ 1 — ПРИОРИТЕТНЫЙ ЧЕК-ЛИСТ
    # ═════════════════════════════════════════════════════════════════════════

    # ──────────────── 1. БАЗОВЫЕ МЕТРИКИ ВЗАИМОДЕЙСТВИЙ ─────────────────────

    def analyze_basic_interactions(self, runs_meta: pd.DataFrame) -> str:
        print("\n📊  [1/9] Базовые метрики взаимодействий…")
        report = _section("1. Базовые метрики взаимодействий")

        # 1a. Суммарное число контактов по сценариям
        df_counts = self._q(
            """
            SELECT
                sr.scenario_name,
                sr.run_name,
                count() AS total_interactions
            FROM interactions i
            JOIN simulation_runs sr ON i.run_id = sr.run_id
            GROUP BY sr.scenario_name, sr.run_name
            ORDER BY sr.scenario_name
            """
        )
        df_counts = df_counts.merge(
            runs_meta[["scenario_name", "init_type", "group", "nonlinear"]],
            on="scenario_name",
            how="left",
        )

        # График — бар-чарт по сценариям
        fig, ax = plt.subplots(figsize=(16, 6))
        colors = [PALETTE_3[INIT_TYPES.index(t)] if t in INIT_TYPES else "grey"
                  for t in df_counts["init_type"]]
        bars = ax.bar(df_counts["scenario_name"], df_counts["total_interactions"] / 1e6,
                      color=colors, edgecolor="white", linewidth=0.5)
        ax.set_title("Суммарное число взаимодействий по сценариям", fontsize=14, fontweight="bold")
        ax.set_xlabel("Сценарий")
        ax.set_ylabel("Число контактов (млн)")
        ax.tick_params(axis="x", rotation=75, labelsize=7)
        # Легенда
        from matplotlib.patches import Patch
        legend_elements = [Patch(facecolor=PALETTE_3[i], label=t) for i, t in enumerate(INIT_TYPES)]
        ax.legend(handles=legend_elements, title="Тип инициализации", loc="upper right")
        fig.tight_layout()
        p1a = _savefig(fig, "1a_total_interactions_per_scenario")

        # 1b. Статистика по группам
        summary = (
            df_counts.groupby(["group", "init_type"])["total_interactions"]
            .agg(["mean", "min", "max", "count"])
            .reset_index()
        )
        summary.columns = ["Группа", "Тип инициализации", "Среднее", "Мин", "Макс", "N"]

        fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=False)
        for ax, grp in zip(axes, ["homogeneous", "heterogeneous"]):
            sub = summary[summary["Группа"] == grp]
            x = np.arange(len(sub))
            ax.bar(x - 0.25, sub["Мин"] / 1e6, width=0.25, label="Мин", color="#90CAF9")
            ax.bar(x,        sub["Среднее"] / 1e6, width=0.25, label="Среднее", color="#1565C0")
            ax.bar(x + 0.25, sub["Макс"] / 1e6, width=0.25, label="Макс", color="#0D47A1")
            ax.set_xticks(x)
            ax.set_xticklabels(sub["Тип инициализации"])
            ax.set_title(f"{'Гомогенные' if grp == 'homogeneous' else 'Гетерогенные'} сценарии")
            ax.set_ylabel("Контактов (млн)")
            ax.legend()
        fig.suptitle("Мин/Среднее/Макс контактов по группам и типу инициализации",
                     fontsize=13, fontweight="bold")
        fig.tight_layout()
        p1b = _savefig(fig, "1b_interactions_group_comparison")

        # 1c. Нелинейность
        nl_df = df_counts.groupby("nonlinear")["total_interactions"].agg(["mean", "std"]).reset_index()
        nl_df["label"] = nl_df["nonlinear"].map({True: "Нелинейные", False: "Линейные"})
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.bar(nl_df["label"], nl_df["mean"] / 1e6,
               yerr=nl_df["std"] / 1e6, capsize=8, color=["#EF5350", "#42A5F5"],
               edgecolor="white")
        ax.set_title("Влияние нелинейности на активность системы", fontsize=13, fontweight="bold")
        ax.set_ylabel("Среднее число контактов (млн)")
        fig.tight_layout()
        p1c = _savefig(fig, "1c_nonlinearity_effect")

        report += _subsection("1a. Суммарные контакты по сценариям")
        report += _img(p1a, "Суммарные контакты по сценариям")
        report += _subsection("1b. Мин/Среднее/Макс по группам")
        report += _img(p1b, "Сравнение контактов по группам и типу инициализации")
        report += "\n" + summary.to_markdown(index=False) + "\n"
        report += _subsection("1c. Нелинейность и активность")
        report += _img(p1c, "Влияние нелинейности на общую активность")
        return report

    # ──────────────── 2. ГЛУБОКИЙ АНАЛИЗ ОТКАЗОВ ─────────────────────────────

    def analyze_refusals(self) -> str:
        print("📊  [2/9] Анализ отказов…")
        report = _section("2. Глубокий анализ отказов")

        # Общий % отказов
        df_global = self._q(
            """
            SELECT
                countIf(type = 0)  AS refusals,
                countIf(type = 1)  AS successes,
                countIf(type = -1) AS failures,
                count()              AS total
            FROM interactions
            """
        )
        refusal_pct = float(df_global["refusals"].iloc[0]) / float(df_global["total"].iloc[0]) * 100
        report += f"\n**Общий процент отказов:** {refusal_pct:.2f}%\n"
        report += "\n" + df_global.to_markdown(index=False) + "\n"

        # Отказы по локациям
        df_loc = self._q(
            """
            SELECT
                multiIf(
                    slot_id IN (1, 3, 5, 7), 'CLASS',
                    slot_id IN (2, 4, 6),    'BREAK',
                    'GYM'
                ) AS location,
                countIf(type = 0) AS refusals,
                count()             AS total,
                round(countIf(type = 0) / count() * 100, 2) AS refusal_pct
            FROM interactions
            GROUP BY location
            ORDER BY refusal_pct DESC
            """
        )
        loc_labels = {"CLASS": "Занятия (CLASS)", "BREAK": "Переменa (BREAK)", "GYM": "Физкультура (GYM)"}
        df_loc["location_ru"] = df_loc["location"].map(loc_labels)

        fig, ax = plt.subplots(figsize=(8, 5))
        bars = ax.bar(df_loc["location_ru"], df_loc["refusal_pct"],
                      color=["#EF5350", "#FF9800", "#42A5F5"], edgecolor="white")
        for bar, val in zip(bars, df_loc["refusal_pct"]):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                    f"{val:.1f}%", ha="center", fontsize=11)
        ax.set_title("Процент отказов по локациям", fontsize=13, fontweight="bold")
        ax.set_ylabel("Доля отказов (%)")
        ax.set_ylim(0, df_loc["refusal_pct"].max() * 1.2)
        fig.tight_layout()
        p2a = _savefig(fig, "2a_refusals_by_location")

        # Распределение отказов по агентам (для кривой Лоренца)
        df_agent_ref = self._q(
            """
            SELECT
                to_id               AS agent_id,
                countIf(type = 0)   AS refusals,
                count()             AS total_as_target
            FROM interactions
            GROUP BY to_id
            ORDER BY refusals DESC
            """
        )
        # Кривая Лоренца
        vals = np.sort(df_agent_ref["refusals"].values)
        n = len(vals)
        lorenz_y = np.cumsum(vals) / vals.sum()
        lorenz_x = np.arange(1, n + 1) / n
        if hasattr(np, "trapezoid"):
            gini = 1 - 2 * np.trapezoid(lorenz_y, lorenz_x)
        else:
            gini = 1 - 2 * np.trapz(lorenz_y, lorenz_x)

        fig, ax = plt.subplots(figsize=(7, 6))
        ax.plot(lorenz_x * 100, lorenz_y * 100, color="#1565C0", lw=2, label="Кривая Лоренца")
        ax.plot([0, 100], [0, 100], "k--", lw=1, label="Абсолютное равенство")
        ax.fill_between(lorenz_x * 100, lorenz_y * 100, lorenz_x * 100, alpha=0.15, color="#1565C0")
        ax.set_title(f"Кривая Лоренца: распределение отказов\n(Коэф. Джини = {gini:.3f})",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Доля агентов (%)")
        ax.set_ylabel("Доля суммарных отказов (%)")
        ax.legend()
        fig.tight_layout()
        p2b = _savefig(fig, "2b_lorenz_curve_refusals")

        # Топ-10% и Топ-50%
        total_ref = vals.sum()
        top10_idx = int(n * 0.9)
        top50_idx = int(n * 0.5)
        pct_top10 = vals[top10_idx:].sum() / total_ref * 100
        pct_top50 = vals[top50_idx:].sum() / total_ref * 100
        zero_refusers = int((df_agent_ref["refusals"] == 0).sum())
        zero_pct = zero_refusers / n * 100

        report += _subsection("2a. Отказы по локациям")
        report += _img(p2a, "Процент отказов по локациям")
        report += "\n" + df_loc.to_markdown(index=False) + "\n"
        report += _subsection("2b. Распределение отказов по агентам")
        report += _img(p2b, "Кривая Лоренца: концентрация отказов")
        report += (
            f"\n- **ТОП-10% «мизантропов»** генерируют **{pct_top10:.1f}%** всех отказов.\n"
            f"- **ТОП-50%** генерируют **{pct_top50:.1f}%** всех отказов.\n"
            f"- Агентов, никогда не отказавших: **{zero_refusers}** ({zero_pct:.1f}%).\n"
            f"- Коэффициент Джини неравенства отказов: **{gini:.3f}**.\n"
        )

        # Отказы по архетипам
        df_arch = self._q(
            """
            SELECT
                ar.archetype,
                countIf(i.type = 0)   AS refusals,
                count()               AS total,
                round(countIf(i.type = 0) / count() * 100, 2) AS refusal_pct
            FROM interactions i
            JOIN agent_registry ar ON i.run_id = ar.run_id AND i.to_id = ar.agent_id
            GROUP BY ar.archetype
            ORDER BY refusal_pct DESC
            """
        )
        fig, ax = plt.subplots(figsize=(10, 5))
        colors_arch = sns.color_palette("RdYlGn_r", len(df_arch))
        bars = ax.barh(df_arch["archetype"], df_arch["refusal_pct"], color=colors_arch)
        for bar, val in zip(bars, df_arch["refusal_pct"]):
            ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}%", va="center", fontsize=9)
        ax.set_title("Процент отказов по архетипам", fontsize=13, fontweight="bold")
        ax.set_xlabel("Доля отказов (%)")
        ax.invert_yaxis()
        fig.tight_layout()
        p2c = _savefig(fig, "2c_refusals_by_archetype")
        report += _subsection("2c. Отказы по архетипам")
        report += _img(p2c, "Процент отказов по архетипам агентов")
        report += "\n" + df_arch.to_markdown(index=False) + "\n"
        return report

    # ──────────────── 3. АНАЛИЗ РЕЛЯЦИОННЫХ ПОРОГОВ ──────────────────────────

    def analyze_relational_thresholds(self, runs_meta: pd.DataFrame) -> str:
        print("📊  [3/9] Анализ реляционных порогов…")
        report = _section("3. Анализ реляционных порогов")

        days_str = ", ".join(str(d) for d in range(30, 1365, 30))
        rows = []
        for idx, row in runs_meta.iterrows():
            run_id = row["run_id"]
            scenario_name = row["scenario_name"]
            # Print progress since sequential execution is easy to track
            print(f"    - Обработка сценария {idx + 1}/{len(runs_meta)}: {scenario_name}")
            query = f"""
            SELECT
                count() AS total_contacts,
                sum(ar.utility >= 5 OR ar.trust >= 5 OR ar.affinity >= 5) AS soft_contacts,
                sum((ar.utility >= 95 AND ar.trust >= 95) OR (ar.utility >= 95 AND ar.affinity >= 95) OR (ar.trust >= 95 AND ar.affinity >= 95)) AS hard_contacts
            FROM interactions i
            LEFT JOIN (
                SELECT run_id, day_id, subject_id, object_id, utility, trust, affinity
                FROM agent_relations
                WHERE run_id = '{run_id}'
                  AND day_id IN ({days_str})
            ) ar
              ON i.run_id = ar.run_id
             AND i.day_id = ar.day_id
             AND i.from_id = ar.subject_id
             AND i.to_id = ar.object_id
            WHERE i.run_id = '{run_id}'
              AND i.day_id IN ({days_str})
            """
            df = self._q(query)
            if df.empty:
                rows.append({
                    "scenario_name": scenario_name,
                    "total_contacts": 0,
                    "soft_contacts": 0,
                    "hard_contacts": 0
                })
            else:
                rows.append({
                    "scenario_name": scenario_name,
                    "total_contacts": int(df["total_contacts"].iloc[0] or 0),
                    "soft_contacts": int(df["soft_contacts"].iloc[0] or 0),
                    "hard_contacts": int(df["hard_contacts"].iloc[0] or 0)
                })

        df_thresh = pd.DataFrame(rows)
        df_thresh["soft_pct"] = np.where(df_thresh["total_contacts"] > 0, df_thresh["soft_contacts"] / df_thresh["total_contacts"] * 100, 0.0)
        df_thresh["hard_pct"] = np.where(df_thresh["total_contacts"] > 0, df_thresh["hard_contacts"] / df_thresh["total_contacts"] * 100, 0.0)
        df_thresh = df_thresh.merge(
            runs_meta[["scenario_name", "init_type"]].drop_duplicates(), on="scenario_name", how="left"
        )

        fig, axes = plt.subplots(1, 2, figsize=(16, 5))
        for ax, col, title in [
            (axes[0], "soft_pct", "Мягкое условие (≥5 по одному параметру)"),
            (axes[1], "hard_pct", "Строгое условие (≥95 по двум параметрам)"),
        ]:
            colors = [PALETTE_3[INIT_TYPES.index(t)] if t in INIT_TYPES else "grey"
                      for t in df_thresh["init_type"]]
            ax.bar(df_thresh["scenario_name"], df_thresh[col], color=colors, edgecolor="white")
            ax.set_title(title, fontsize=11, fontweight="bold")
            ax.set_ylabel("% контактов")
            ax.tick_params(axis="x", rotation=75, labelsize=7)
        from matplotlib.patches import Patch
        legend_elements = [Patch(facecolor=PALETTE_3[i], label=t) for i, t in enumerate(INIT_TYPES)]
        axes[1].legend(handles=legend_elements, title="Тип инициализации")
        fig.suptitle("Доля контактов при устойчивых реляционных связях", fontsize=13, fontweight="bold")
        fig.tight_layout()
        p3a = _savefig(fig, "3a_relational_threshold_contacts")

        # Среднее по типам инициализации
        summary = (
            df_thresh.groupby("init_type")[["soft_pct", "hard_pct"]]
            .agg(["mean", "std"])
            .reset_index()
        )

        report += _img(p3a, "Доля контактов при реляционных порогах по сценариям")
        report += "\n" + df_thresh[["scenario_name", "init_type", "soft_pct", "hard_pct"]].to_markdown(index=False) + "\n"
        report += _subsection("Среднее по типам инициализации")
        report += "\n" + summary.to_markdown() + "\n"
        return report

    # ──────────────── 4. СТАБИЛЬНЫЕ ПАРЫ ─────────────────────────────────────

    def analyze_stable_pairs(self, rep_run_id: str) -> str:
        print("📊  [4/9] Стабильные пары…")
        report = _section("4. Стабильные пары")

        # Семестровые бины (каждые ~170 дней = 1 семестр, 1365 / 8 ≈ 171)
        semester_size = 171
        n_semesters = 8

        results = {}
        for threshold in STABILITY_THRESHOLDS:
            thr_label = f"{threshold*100:.1f}%"
            # Считаем по семестрам: для каждой пары агентов — доля взаимных встреч
            # За каждый семестр находим пары, где взаимная доля >= threshold
            rows = []
            for sem in range(1, n_semesters + 1):
                day_from = (sem - 1) * semester_size + 1
                day_to = sem * semester_size

                df_sem = self._q(
                    f"""
                    SELECT
                        greatest(from_id, to_id) AS a,
                        least(from_id, to_id)    AS b,
                        count()                  AS total_contacts
                    FROM interactions
                    WHERE run_id = '{rep_run_id}'
                      AND day_id BETWEEN {day_from} AND {day_to}
                    GROUP BY a, b
                    HAVING count() >= 3
                    """
                )
                if df_sem.empty:
                    rows.append({"semester": sem, "stable_pairs": 0})
                    continue

                df_sem2 = self._q(
                    f"""
                    WITH pairs AS (
                        SELECT
                            greatest(from_id, to_id) AS a,
                            least(from_id, to_id)    AS b,
                            count()                  AS pair_contacts
                        FROM interactions
                        WHERE run_id = '{rep_run_id}'
                          AND day_id BETWEEN {day_from} AND {day_to}
                        GROUP BY a, b
                    ),
                    agent_contacts AS (
                        SELECT from_id AS agent, count() AS total
                        FROM interactions
                        WHERE run_id = '{rep_run_id}'
                          AND day_id BETWEEN {day_from} AND {day_to}
                        GROUP BY from_id
                    ),
                    agent_contacts2 AS (
                        SELECT to_id AS agent, count() AS total
                        FROM interactions
                        WHERE run_id = '{rep_run_id}'
                          AND day_id BETWEEN {day_from} AND {day_to}
                        GROUP BY to_id
                    ),
                    agent_total AS (
                        SELECT agent, sum(total) AS total
                        FROM (
                            SELECT * FROM agent_contacts
                            UNION ALL
                            SELECT * FROM agent_contacts2
                        )
                        GROUP BY agent
                    )
                    SELECT
                        p.a, p.b,
                        p.pair_contacts,
                        at_a.total AS total_a,
                        at_b.total AS total_b,
                        p.pair_contacts / (at_a.total + at_b.total - p.pair_contacts) AS jaccard
                    FROM pairs p
                    JOIN agent_total at_a ON p.a = at_a.agent
                    JOIN agent_total at_b ON p.b = at_b.agent
                    WHERE p.pair_contacts / (at_a.total + at_b.total - p.pair_contacts) >= {threshold}
                    """
                )
                rows.append({"semester": sem, "stable_pairs": len(df_sem2)})
            results[thr_label] = pd.DataFrame(rows)

        fig, ax = plt.subplots(figsize=(10, 6))
        colors_thr = ["#1565C0", "#2E7D32", "#E65100", "#6A1B9A"]
        for (label, df_r), color in zip(results.items(), colors_thr):
            ax.plot(df_r["semester"], df_r["stable_pairs"],
                    marker="o", label=f"Порог {label}", color=color, lw=2)
        ax.set_title("Динамика стабильных пар по семестрам", fontsize=13, fontweight="bold")
        ax.set_xlabel("Семестр")
        ax.set_ylabel("Количество стабильных пар")
        ax.set_xticks(range(1, n_semesters + 1))
        ax.set_xticklabels([f"С{i}" for i in range(1, n_semesters + 1)])
        ax.legend(title="Порог стабильности")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        p4 = _savefig(fig, "4_stable_pairs_dynamics")

        report += _img(p4, "Динамика стабильных пар по семестрам")
        for label, df_r in results.items():
            report += f"\n**Порог {label}:**\n"
            report += df_r.to_markdown(index=False) + "\n"
        return report

    # ──────────────── 5. ЭМОЦИОНАЛЬНЫЙ ФОН ──────────────────────────────────

    def analyze_emotional_background(self, rep_run_id: str) -> str:
        print("📊  [5/9] Эмоциональный фон…")
        report = _section("5. Эмоциональный фон коллектива")

        # Средние эмоции по дням (агрегация на стороне ClickHouse)
        emotions_sql = ", ".join([f"avg({e}) AS {e}" for e in EMOTION_AXES])
        df_emo = self._q(
            f"""
            SELECT
                day_id,
                {emotions_sql}
            FROM agent_states
            WHERE run_id = '{rep_run_id}'
            GROUP BY day_id
            ORDER BY day_id
            """
        )

        # 5a. Временные ряды
        fig, axes = plt.subplots(4, 2, figsize=(14, 16), sharex=True)
        axes_flat = axes.flatten()
        for i, (col, label) in enumerate(EMOTION_LABELS.items()):
            ax = axes_flat[i]
            ax.plot(df_emo["day_id"], df_emo[col], color=PALETTE[i], lw=1.2)
            # Скользящее среднее (окно 30 дней)
            rolling = df_emo[col].rolling(window=30, center=True).mean()
            ax.plot(df_emo["day_id"], rolling, color="black", lw=2, linestyle="--", label="MA-30")
            ax.set_title(label, fontsize=10)
            ax.set_ylabel("Среднее значение")
            ax.axhline(0, color="grey", lw=0.8, linestyle=":")
            ax.legend(fontsize=8)
        axes_flat[-1].set_visible(False)
        for ax in axes_flat[-2:]:
            ax.set_xlabel("День симуляции")
        fig.suptitle("Динамика среднего эмоционального фона коллектива\n(7 осей, 1365 дней)",
                     fontsize=14, fontweight="bold")
        fig.tight_layout()
        p5a = _savefig(fig, "5a_emotional_dynamics")

        # 5b. Оценка стабилизации — последние 200 дней vs первые 200
        early = df_emo[df_emo["day_id"] <= 200][EMOTION_AXES].mean()
        late = df_emo[df_emo["day_id"] >= 1165][EMOTION_AXES].mean()
        drift = (late - early).abs()

        fig, ax = plt.subplots(figsize=(9, 5))
        x = np.arange(len(EMOTION_AXES))
        w = 0.35
        ax.bar(x - w / 2, early.values, w, label="Первые 200 дней", color="#90CAF9")
        ax.bar(x + w / 2, late.values,  w, label="Последние 200 дней", color="#1565C0")
        ax.set_xticks(x)
        ax.set_xticklabels([EMOTION_LABELS[e] for e in EMOTION_AXES], rotation=40, ha="right")
        ax.set_title("Эмоциональный фон: начало vs конец симуляции", fontsize=12, fontweight="bold")
        ax.set_ylabel("Среднее значение оси")
        ax.legend()
        fig.tight_layout()
        p5b = _savefig(fig, "5b_emotional_stabilization")

        # 5c. Тепловая карта (день × эмоция)
        # Разобьём на 50 временных бинов для наглядности
        df_emo["bin"] = pd.cut(df_emo["day_id"], bins=50, labels=False)
        heatmap_data = df_emo.groupby("bin")[EMOTION_AXES].mean().T
        heatmap_data.index = [EMOTION_LABELS[e] for e in EMOTION_AXES]

        fig, ax = plt.subplots(figsize=(16, 5))
        sns.heatmap(
            heatmap_data,
            ax=ax,
            cmap="RdYlGn",
            center=0,
            vmin=-15, vmax=15,
            linewidths=0.2,
            cbar_kws={"label": "Среднее значение [-30, 30]"},
        )
        ax.set_title("Тепловая карта доминирующих эмоций во времени", fontsize=13, fontweight="bold")
        ax.set_xlabel("Временной бин (1–50, весь период симуляции)")
        ax.set_ylabel("Эмоциональная ось")
        fig.tight_layout()
        p5c = _savefig(fig, "5c_emotional_heatmap")

        report += _img(p5a, "Временные ряды эмоционального фона по 7 осям")
        report += _img(p5b, "Начало vs конец симуляции: сравнение эмоций")
        report += _img(p5c, "Тепловая карта эмоций во времени")

        report += "\n**Дрейф осей (|среднее последних 200 дней − первых 200 дней|):**\n"
        report += drift.rename(EMOTION_LABELS).to_frame("Δ дрейф").to_markdown() + "\n"
        return report

    # ═════════════════════════════════════════════════════════════════════════
    #  ЧАСТЬ 2 — СКРЫТЫЕ ЗАКОНОМЕРНОСТИ
    # ═════════════════════════════════════════════════════════════════════════

    # ──────────────── 6. ЭФФЕКТ «ВЫГОРАНИЯ ЛИДЕРА» ───────────────────────────

    def analyze_leader_burnout(self, rep_run_id: str) -> str:
        print("📊  [6/9] Эффект «Выгорания лидера»…")
        report = _section("6. Эффект «Выгорания лидера» (Popularity-Induced Burnout)")

        days_str = ", ".join(str(d) for d in range(30, 1365, 30))
        # Входящая популярность: число агентов, у кого trust >= 80 AND affinity >= 80
        df_pop = self._q(
            f"""
            SELECT
                object_id AS agent_id,
                countIf(trust >= 80 AND affinity >= 80) AS fans
            FROM agent_relations
            WHERE run_id = '{rep_run_id}'
              AND day_id IN ({days_str})
            GROUP BY object_id
            ORDER BY fans DESC
            """
        )

        # Средние эмоции по агентам
        emotions_sql = ", ".join([f"avg({e}) AS {e}" for e in ["anger_humility", "fear_calm", "sadness_joy"]])
        df_emo_agents = self._q(
            f"""
            SELECT
                agent_id,
                {emotions_sql}
            FROM agent_states
            WHERE run_id = '{rep_run_id}'
            GROUP BY agent_id
            """
        )

        df_merged = df_pop.merge(df_emo_agents, on="agent_id", how="inner")

        # Корреляции Пирсона
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        emotions_burnout = [
            ("anger_humility", "Гнев–Смирение (негатив ↓)"),
            ("fear_calm",      "Страх–Спокойствие (негатив ↓)"),
            ("sadness_joy",    "Печаль–Радость (негатив ↓)"),
        ]
        correlations = {}
        for ax, (col, label) in zip(axes, emotions_burnout):
            r, p = stats.pearsonr(df_merged["fans"], df_merged[col])
            correlations[col] = (r, p)
            ax.scatter(df_merged["fans"], df_merged[col],
                       alpha=0.3, s=10, color="#1565C0")
            # Линия тренда
            z = np.polyfit(df_merged["fans"], df_merged[col], 1)
            poly = np.poly1d(z)
            xline = np.linspace(df_merged["fans"].min(), df_merged["fans"].max(), 100)
            ax.plot(xline, poly(xline), "r-", lw=2)
            ax.set_title(f"{label}\nr={r:.3f}, p={p:.4f}", fontsize=10)
            ax.set_xlabel("Входящая популярность (кол-во «фанатов»)")
            ax.set_ylabel("Среднее значение оси")
        fig.suptitle("Корреляция популярности с негативными эмоциями лидеров",
                     fontsize=13, fontweight="bold")
        fig.tight_layout()
        p6 = _savefig(fig, "6_leader_burnout_correlation")

        report += _img(p6, "Корреляция входящей популярности с эмоциональным состоянием лидеров")
        for col, (r, p) in correlations.items():
            significance = "✅ значимо" if p < 0.05 else "❌ незначимо"
            report += f"\n- **{EMOTION_LABELS[col]}**: r = {r:.3f}, p = {p:.4f} ({significance})\n"

        # Динамика: группируем лидеров (топ-10%) vs остальных по дням
        fan_cutoff = float(df_pop["fans"].quantile(0.90))
        top_agents = df_pop[df_pop["fans"] >= fan_cutoff]["agent_id"].tolist()
        top_agents_str = ", ".join(map(str, top_agents[:500]))  # безопасный лимит для IN

        if top_agents_str:
            df_dyn = self._q(
                f"""
                SELECT
                    day_id,
                    avg(anger_humility) AS anger_top,
                    avg(fear_calm)      AS fear_top,
                    avg(sadness_joy)    AS sadness_top
                FROM agent_states
                WHERE run_id = '{rep_run_id}'
                  AND agent_id IN ({top_agents_str})
                GROUP BY day_id
                ORDER BY day_id
                """
            )
            df_dyn_all = self._q(
                f"""
                SELECT
                    day_id,
                    avg(anger_humility) AS anger_all,
                    avg(sadness_joy)    AS sadness_all
                FROM agent_states
                WHERE run_id = '{rep_run_id}'
                GROUP BY day_id
                ORDER BY day_id
                """
            )
            df_dyn_merged = df_dyn.merge(df_dyn_all, on="day_id", how="inner")

            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(df_dyn_merged["day_id"], df_dyn_merged["anger_top"],
                    color="#EF5350", lw=1.5, label="Гнев: ТОП-10% популярных")
            ax.plot(df_dyn_merged["day_id"], df_dyn_merged["anger_all"],
                    color="#FFCDD2", lw=1.5, linestyle="--", label="Гнев: все агенты")
            ax.plot(df_dyn_merged["day_id"], df_dyn_merged["sadness_top"],
                    color="#1565C0", lw=1.5, label="Печаль: ТОП-10% популярных")
            ax.plot(df_dyn_merged["day_id"], df_dyn_merged["sadness_all"],
                    color="#90CAF9", lw=1.5, linestyle="--", label="Печаль: все агенты")
            ax.set_title("Эмоциональная динамика: лидеры vs всё сообщество",
                         fontsize=12, fontweight="bold")
            ax.set_xlabel("День симуляции")
            ax.set_ylabel("Среднее значение оси")
            ax.legend(fontsize=9)
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            p6b = _savefig(fig, "6b_leader_burnout_dynamics")
            report += _img(p6b, "Эмоциональная динамика: лидеры vs сообщество")
        return report

    # ──────────────── 7. АТТРАКТОРНАЯ СХОДИМОСТЬ ────────────────────────────

    def analyze_attractor_convergence(self, runs_meta: pd.DataFrame) -> str:
        print("📊  [7/9] Аттракторная сходимость…")
        report = _section("7. «Аттракторная сходимость» сетей (Topological Memory)")

        # Финальные матрицы: среднее Trust между архетипами на последних 50 днях
        matrices = {}
        for _, row in runs_meta.iterrows():
            rid = row["run_id"]
            df_mat = self._q(
                f"""
                SELECT
                    ar1.archetype AS arch_from,
                    ar2.archetype AS arch_to,
                    avg(rel.trust) AS avg_trust
                FROM agent_relations rel
                JOIN agent_registry ar1 ON rel.run_id = ar1.run_id AND rel.subject_id = ar1.agent_id
                JOIN agent_registry ar2 ON rel.run_id = ar2.run_id AND rel.object_id  = ar2.agent_id
                WHERE rel.run_id = '{rid}'
                  AND rel.day_id >= 1315
                GROUP BY arch_from, arch_to
                """
            )
            if not df_mat.empty:
                pivot = df_mat.pivot_table(index="arch_from", columns="arch_to",
                                           values="avg_trust", aggfunc="mean").fillna(0)
                matrices[row["scenario_name"]] = pivot

        # Попарное косинусное сходство между сценариями с одинаковой группой архетипов
        # Группируем по run_name (одинаковый состав архетипов) — разный стартовый тип
        run_groups = runs_meta.groupby("run_name")["scenario_name"].apply(list).to_dict()

        similarity_records = []
        for run_name, scenarios in run_groups.items():
            pairs = [(s1, s2) for i, s1 in enumerate(scenarios)
                     for s2 in scenarios[i + 1:] if s1 in matrices and s2 in matrices]
            for s1, s2 in pairs:
                m1 = matrices[s1]
                m2 = matrices[s2]
                # Align по одинаковым архетипам
                common_rows = m1.index.intersection(m2.index)
                common_cols = m1.columns.intersection(m2.columns)
                if len(common_rows) < 2 or len(common_cols) < 2:
                    continue
                v1 = m1.loc[common_rows, common_cols].values.flatten()
                v2 = m2.loc[common_rows, common_cols].values.flatten()
                if v1.std() < 1e-9 or v2.std() < 1e-9:
                    cos_sim = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))
                    pearson = float(np.nan)
                else:
                    cos_sim = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))
                    pearson, _ = stats.pearsonr(v1, v2)
                similarity_records.append({
                    "run_name": run_name,
                    "scenario_1": s1,
                    "scenario_2": s2,
                    "cosine_similarity": cos_sim,
                    "pearson_r": pearson,
                })

        df_sim = pd.DataFrame(similarity_records)

        if not df_sim.empty:
            fig, ax = plt.subplots(figsize=(10, 5))
            sns.boxplot(data=df_sim, x="run_name", y="pearson_r",
                        palette="Set2", ax=ax)
            ax.axhline(1.0, color="green", lw=1.5, linestyle="--", label="Полная сходимость (r=1)")
            ax.axhline(0.5, color="orange", lw=1.5, linestyle=":", label="Умеренная сходимость (r=0.5)")
            ax.set_title("Сходимость финальных матриц отношений (одинаковые архетипы,\nразный старт)",
                         fontsize=12, fontweight="bold")
            ax.set_xlabel("Серия (Run)")
            ax.set_ylabel("Корреляция Пирсона финальных Trust-матриц")
            ax.tick_params(axis="x", rotation=45)
            ax.legend()
            fig.tight_layout()
            p7 = _savefig(fig, "7_attractor_convergence")
            report += _img(p7, "Аттракторная сходимость: корреляция финальных матриц")
            report += "\n" + df_sim.describe().to_markdown() + "\n"
        else:
            report += "\n*Недостаточно данных для сравнения (менее 2 архетипов).*\n"
        return report

    # ──────────────── 8. ЭМОЦИОНАЛЬНЫЕ ПУЗЫРИ ────────────────────────────────

    def analyze_emotional_bubbles(self, rep_run_id: str) -> str:
        print("📊  [8/9] Эмоциональные пузыри…")
        report = _section("8. Эмоциональные пузыри (Emotional Contagion & Clustering)")

        # Для каждого агента — топ-3 друга по affinity (по последним 100 дням)
        df_friends = self._q(
            f"""
            SELECT
                subject_id AS agent_id,
                object_id  AS friend_id,
                avg(affinity) AS avg_affinity
            FROM agent_relations
            WHERE run_id = '{rep_run_id}'
              AND day_id >= 1265
            GROUP BY subject_id, object_id
            QUALIFY row_number() OVER (PARTITION BY subject_id ORDER BY avg_affinity DESC) <= 3
            """
        )

        # Эмоции агентов (последние 100 дней)
        emotions_sql = ", ".join([f"avg({e}) AS {e}" for e in EMOTION_AXES])
        df_emo_agents = self._q(
            f"""
            SELECT agent_id, {emotions_sql}
            FROM agent_states
            WHERE run_id = '{rep_run_id}'
              AND day_id >= 1265
            GROUP BY agent_id
            """
        )

        # Средние эмоции топ-3 друзей
        df_friend_emo = (
            df_friends.merge(df_emo_agents.rename(
                columns={e: f"friend_{e}" for e in EMOTION_AXES}
            ).rename(columns={"agent_id": "friend_id"}),
                on="friend_id", how="inner")
            .groupby("agent_id")[[f"friend_{e}" for e in EMOTION_AXES]]
            .mean()
            .reset_index()
        )

        df_ego = df_emo_agents.merge(df_friend_emo, on="agent_id", how="inner")

        # Ассортативность: корреляция по каждой оси
        assort_results = {}
        for e in EMOTION_AXES:
            if df_ego[[e, f"friend_{e}"]].dropna().shape[0] < 10:
                continue
            r, p = stats.pearsonr(df_ego[e], df_ego[f"friend_{e}"])
            assort_results[EMOTION_LABELS[e]] = {"r": r, "p": p}

        df_assort = pd.DataFrame(assort_results).T
        df_assort["significant"] = df_assort["p"] < 0.05

        fig, ax = plt.subplots(figsize=(10, 5))
        colors_sig = ["#4CAF50" if s else "#EF5350" for s in df_assort["significant"]]
        bars = ax.barh(df_assort.index, df_assort["r"], color=colors_sig, edgecolor="white")
        ax.axvline(0, color="black", lw=0.8)
        for bar, (_, row_) in zip(bars, df_assort.iterrows()):
            label = f"r={row_['r']:.3f}" + (" *" if row_["significant"] else "")
            ax.text(bar.get_width() + 0.005 * np.sign(bar.get_width()),
                    bar.get_y() + bar.get_height() / 2,
                    label, va="center", fontsize=9)
        ax.set_title("Ассортативность по эмоциям\n(корреляция «эго–среднее топ-3 друзей»)",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Коэффициент корреляции Пирсона")
        ax.invert_yaxis()
        from matplotlib.patches import Patch
        ax.legend(handles=[
            Patch(facecolor="#4CAF50", label="p < 0.05 (значимо)"),
            Patch(facecolor="#EF5350", label="p ≥ 0.05 (незначимо)"),
        ])
        fig.tight_layout()
        p8 = _savefig(fig, "8_emotional_bubbles_assortivity")

        report += _img(p8, "Эмоциональная ассортативность: эго vs друзья")
        report += "\n" + df_assort.to_markdown() + "\n"
        report += (
            "\n**Интерпретация:** Положительный r означает, что агенты с определённым эмоциональным профилем\n"
            "дружат с похожими агентами — подтверждая гипотезу об «эмоциональных пузырях».\n"
        )
        return report

    # ──────────────── 9. СКОРОСТЬ ПОЛУРАСПАДА ОТНОШЕНИЙ ──────────────────────

    def analyze_relational_halflife(self) -> str:
        print("📊  [9/9] Скорость полураспада отношений…")
        report = _section("9. Скорость полураспада отношений (Relational Half-Life by Archetype)")

        # Находим пары, которые в последние 200 дней больше не встречались
        # (последний совместный день < 1165), и смотрим угасание trust/affinity
        df_last_contact = self._q(
            """
            SELECT
                run_id,
                greatest(from_id, to_id) AS a,
                least(from_id, to_id)    AS b,
                max(day_id)              AS last_day
            FROM interactions
            GROUP BY run_id, a, b
            HAVING last_day < 1165 AND last_day > 200
            LIMIT 20000
            """
        )
        if df_last_contact.empty:
            return report + "\n*Нет данных о «угасших» парах.*\n"

        # Для каждой пары берём динамику trust по дням
        # Агрегируем: по дням до last_day — средний trust у выбранных пар
        # Упрощённо: строим средний профиль угасания (нормируем day → day - last_contact_day)
        # Делаем для образца первых 500 пар
        sample_pairs = df_last_contact.head(500)

        # Собираем run_id → list (a, b, last_day)
        from collections import defaultdict
        run_pairs: dict = defaultdict(list)
        for _, row in sample_pairs.iterrows():
            run_pairs[row["run_id"]].append((int(row["a"]), int(row["b"]), int(row["last_day"])))

        decay_rows = []
        for run_id, pairs in list(run_pairs.items())[:5]:  # берём 5 серий
            pairs_cond = " OR ".join(
                [f"(subject_id = {a} AND object_id = {b})" for a, b, _ in pairs[:100]]
            )
            max_last = max(ld for _, _, ld in pairs)
            df_rel = self._q(
                f"""
                SELECT
                    day_id,
                    subject_id,
                    object_id,
                    trust,
                    affinity
                FROM agent_relations
                WHERE run_id = '{run_id}'
                  AND ({pairs_cond})
                  AND day_id <= {max_last}
                ORDER BY subject_id, object_id, day_id
                """
            )
            if df_rel.empty:
                continue
            for (a, b, last_day) in pairs[:100]:
                sub = df_rel[
                    (df_rel["subject_id"] == a) & (df_rel["object_id"] == b)
                ].copy()
                if sub.empty:
                    continue
                sub["days_before_end"] = last_day - sub["day_id"]
                sub = sub[sub["days_before_end"] >= 0]
                sub["run_id"] = run_id
                decay_rows.append(sub[["days_before_end", "trust", "affinity", "run_id"]])

        if not decay_rows:
            return report + "\n*Недостаточно данных для анализа угасания.*\n"

        df_decay = pd.concat(decay_rows, ignore_index=True)
        df_decay["bin"] = pd.cut(df_decay["days_before_end"], bins=20, labels=False)
        df_agg = df_decay.groupby("bin")[["trust", "affinity"]].mean().reset_index()
        df_agg = df_agg.sort_values("bin", ascending=False)  # bin 0 = последний день

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(df_agg["bin"], df_agg["trust"], color="#1565C0", lw=2, marker="o", label="Доверие (trust)")
        ax.plot(df_agg["bin"], df_agg["affinity"], color="#2E7D32", lw=2, marker="s", label="Симпатия (affinity)")
        ax.axhline(0, color="red", lw=1, linestyle="--", label="Нейтральный уровень (0)")
        ax.set_title("Профиль угасания отношений до прекращения контактов",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Дней до последнего контакта (бин 0 = непосредственно перед концом)")
        ax.set_ylabel("Среднее значение параметра")
        ax.legend()
        ax.invert_xaxis()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        p9a = _savefig(fig, "9a_relational_decay_profile")

        # По архетипам
        if run_pairs:
            sampled_runs_str = ", ".join(f"'{r}'" for r in list(run_pairs.keys()))
            df_arch_decay = self._q(
                f"""
                WITH broken_pairs AS (
                    SELECT
                        run_id,
                        greatest(from_id, to_id) AS a,
                        least(from_id, to_id)    AS b,
                        max(day_id) AS last_day
                    FROM interactions
                    WHERE run_id IN ({sampled_runs_str})
                    GROUP BY run_id, a, b
                    HAVING last_day < 1165 AND last_day > 200
                )
                SELECT
                    ar.archetype,
                    avg(rel.trust) AS avg_trust_at_end,
                    avg(rel.affinity) AS avg_affinity_at_end,
                    count() AS pairs_count
                FROM broken_pairs bp
                JOIN agent_registry ar ON bp.run_id = ar.run_id AND bp.a = ar.agent_id
                JOIN agent_relations rel ON bp.run_id = rel.run_id
                    AND rel.subject_id = bp.a
                    AND rel.object_id = bp.b
                    AND rel.day_id = bp.last_day
                WHERE rel.run_id IN ({sampled_runs_str})
                GROUP BY ar.archetype
                ORDER BY avg_trust_at_end
                """
            )
        else:
            df_arch_decay = pd.DataFrame()

        if not df_arch_decay.empty:
            fig, ax = plt.subplots(figsize=(10, 5))
            x = np.arange(len(df_arch_decay))
            ax.bar(x - 0.2, df_arch_decay["avg_trust_at_end"], 0.4,
                   label="Trust при последнем контакте", color="#42A5F5")
            ax.bar(x + 0.2, df_arch_decay["avg_affinity_at_end"], 0.4,
                   label="Affinity при последнем контакте", color="#66BB6A")
            ax.set_xticks(x)
            ax.set_xticklabels(df_arch_decay["archetype"], rotation=40, ha="right")
            ax.axhline(0, color="red", lw=1, linestyle="--")
            ax.set_title("Уровень отношений при «распаде» пары по архетипам",
                         fontsize=12, fontweight="bold")
            ax.set_ylabel("Среднее значение параметра при последнем контакте")
            ax.legend()
            fig.tight_layout()
            p9b = _savefig(fig, "9b_relational_decay_by_archetype")
            report += _img(p9a, "Профиль угасания отношений перед прекращением контактов")
            report += _img(p9b, "Уровень отношений при распаде пары по архетипам")
            report += "\n" + df_arch_decay.to_markdown(index=False) + "\n"
        else:
            report += _img(p9a, "Профиль угасания отношений перед прекращением контактов")
        return report

    # ═════════════════════════════════════════════════════════════════════════
    #  ГЕНЕРАЦИЯ ОТЧЁТА И ТОЧКА ВХОДА
    # ═════════════════════════════════════════════════════════════════════════

    def _save_report(self) -> None:
        report_path = OUTPUT_DIR / "research_report.md"
        header = textwrap.dedent(f"""
            # Аналитический отчёт: Многоагентная симуляция социально-эмоциональных отношений

            **Дата генерации:** {self._generated_at}
            **База данных:** ClickHouse (локальный)
            **Объём данных:** 42 серии × 1365 дней, ~56 млрд строк отношений,
            90 млн состояний агентов, 147 млн взаимодействий.

            ---
        """).strip()
        full_report = header + "\n" + "\n".join(self._report_parts)
        report_path.write_text(full_report, encoding="utf-8")
        print(f"\n📝  Отчёт сохранён: {report_path}")

    def run_all(self) -> None:
        """Запустить все анализы последовательно."""
        print("\n" + "═" * 60)
        print("  ResearchAnalyzer — запуск полного анализа")
        print("═" * 60)

        runs_meta = self._load_runs_meta()
        print(f"   Загружено сценариев: {len(runs_meta)}")

        # Найдём репрезентативный run_id для детального анализа (предпочтительно MIXED или RANDOM)
        mixed_runs = runs_meta[runs_meta["scenario_name"].str.contains("MIXED", na=False)]
        if not mixed_runs.empty:
            rep_run_id = mixed_runs["run_id"].iloc[0]
        else:
            rep_run_id = runs_meta["run_id"].iloc[0]

        analyses = [
            lambda: self.analyze_basic_interactions(runs_meta),
            lambda: self.analyze_refusals(),
            lambda: self.analyze_relational_thresholds(runs_meta),
            lambda: self.analyze_stable_pairs(rep_run_id),
            lambda: self.analyze_emotional_background(rep_run_id),
            lambda: self.analyze_leader_burnout(rep_run_id),
            lambda: self.analyze_attractor_convergence(runs_meta),
            lambda: self.analyze_emotional_bubbles(rep_run_id),
            lambda: self.analyze_relational_halflife(),
        ]

        for fn in analyses:
            try:
                section_text = fn()
                self._report_parts.append(section_text)
            except Exception as exc:
                import traceback
                err_msg = traceback.format_exc()
                print(f"   ⚠️  Ошибка в секции: {exc}")
                self._report_parts.append(f"\n\n> ⚠️ **Ошибка выполнения:** `{exc}`\n\n```\n{err_msg}\n```\n")

        self._save_report()
        print("\n✅  Анализ завершён. Графики в:", PLOTS_DIR)
        print("═" * 60 + "\n")


# ─────────────────────────────── ТОЧКА ВХОДА ─────────────────────────────────

if __name__ == "__main__":
    analyzer = ResearchAnalyzer(
        host="localhost",
        port=8123,
        username="default",
        password="clickhouse_pass",
    )
    analyzer.run_all()
