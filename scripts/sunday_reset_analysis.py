"""
sunday_reset_analysis.py
========================
Гипотеза «Эффект воскресного сброса»:
    Агенты с хронически отрицательным эмоциональным фоном восстанавливаются
    после еженедельного δ-сдвига МЕДЛЕННЕЕ, чем нейтральные — потому что
    одинаковый δ «упирается в потолок» у счастливых и лишь ненадолго
    поднимает несчастных, после чего затухание (dE = 0.2 · si) тянет их назад.

Структура модуля:
    1. SundayResetAnalyzer — основной класс
    2. SQL-запросы (агрегация на стороне ClickHouse)
    3. Расчёт метрик восстановления (Recovery Score, Half-Recovery Time)
    4. Визуализация (6 графиков)
    5. Дополнение к research_report.md
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Optional

import clickhouse_connect
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from scipy.optimize import curve_fit

# ──────────────────────────────── КОНФИГУРАЦИЯ ───────────────────────────────

PLOTS_DIR = Path("data/plots")
OUTPUT_DIR = Path("data/output")
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DPI = 200

# В модели 6 учебных дней в неделю → воскресенье каждые 7 дней
# day_id % 7 == 0 соответствует воскресеньям (день 7, 14, 21, ...)
WEEK_LEN = 7
SUNDAY_MOD = 0  # day_id % 7 == 0

# Пороги классификации агентов по базовому эмоциональному фону
# (среднее по всем осям за первые 50 дней до первого воскресного сброса)
CHRONIC_NEGATIVE_THRESHOLD = -5.0   # «Хронически негативные»
CHRONIC_POSITIVE_THRESHOLD = 5.0    # «Хронически позитивные»
# Остальные — «нейтральные»

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
    "sadness_joy":         "Печаль–Радость",
    "fear_calm":           "Страх–Спокойствие",
    "anger_humility":      "Гнев–Смирение",
    "disgust_acceptance":  "Отвращение–Принятие",
    "habit_surprise":      "Привычка–Удивление",
    "shame_confidence":    "Стыд–Уверенность",
    "alienation_openness": "Отчуждение–Открытость",
}

# Цвета групп
COLOR_NEGATIVE = "#E53935"   # красный — хронически негативные
COLOR_NEUTRAL  = "#757575"   # серый   — нейтральные
COLOR_POSITIVE = "#43A047"   # зелёный — хронически позитивные

PALETTE = {
    "negative": COLOR_NEGATIVE,
    "neutral":  COLOR_NEUTRAL,
    "positive": COLOR_POSITIVE,
}
LABEL = {
    "negative": "Хронически негативные",
    "neutral":  "Нейтральные",
    "positive": "Хронически позитивные",
}


# ─────────────────────────────── УТИЛИТЫ ─────────────────────────────────────

def _savefig(fig: plt.Figure, name: str) -> str:
    png = PLOTS_DIR / f"{name}.png"
    pdf = PLOTS_DIR / f"{name}.pdf"
    fig.savefig(png, dpi=DPI, bbox_inches="tight")
    fig.savefig(pdf, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(png)


def _exponential_decay(t: np.ndarray, A: float, lam: float, C: float) -> np.ndarray:
    """Модель экспоненциального затухания: f(t) = A * exp(-λ * t) + C"""
    return A * np.exp(-lam * t) + C


def _half_recovery_time(A: float, lam: float) -> float:
    """Время полувосстановления: t при котором f(t) = A/2 + C → t = ln(2)/λ"""
    if lam <= 0:
        return np.inf
    return np.log(2) / lam


# ─────────────────────────────── ОСНОВНОЙ КЛАСС ──────────────────────────────

class SundayResetAnalyzer:
    """
    Анализ эффекта воскресного сброса эмоций.

    Использование:
        analyzer = SundayResetAnalyzer()
        analyzer.run()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        username: str = "default",
        password: str = "clickhouse_pass",
    ) -> None:
        self.client = clickhouse_connect.get_client(
            host=host, port=port, username=username, password=password
        )
        print("✅  Подключение к ClickHouse установлено.")

    def _q(self, sql: str) -> pd.DataFrame:
        return self.client.query_df(sql)

    # ─────────────────── ШАГ 1: КЛАССИФИКАЦИЯ АГЕНТОВ ────────────────────────

    def _classify_agents(self) -> pd.DataFrame:
        """
        Классифицирует каждого агента по базовому эмоциональному фону.

        Базовый фон = среднее по всем 7 осям за дни 1–6
        (до первого воскресного сброса, чтобы не смешивать).

        SQL: агрегация на стороне ClickHouse — в Python приходит
        таблица размером ~1620 строк.
        """
        print("\n[1/6] Классификация агентов по базовому эмоциональному фону…")

        emotions_avg = " + ".join([f"avg({e})" for e in EMOTION_AXES])
        sql = f"""
            SELECT
                run_id,
                agent_id,
                -- Средний фон по всем 7 осям до первого сброса
                ({emotions_avg}) / 7.0 AS baseline_mood,
                -- Индивидуальные оси для детального анализа
                {", ".join([f"avg({e}) AS base_{e}" for e in EMOTION_AXES])}
            FROM agent_states
            WHERE day_id BETWEEN 1 AND 6
            GROUP BY run_id, agent_id
        """
        df = self._q(sql)

        df["group"] = pd.cut(
            df["baseline_mood"],
            bins=[-30, CHRONIC_NEGATIVE_THRESHOLD, CHRONIC_POSITIVE_THRESHOLD, 30],
            labels=["negative", "neutral", "positive"],
        ).astype(str)

        counts = df["group"].value_counts()
        print(f"   Хронически негативные : {counts.get('negative', 0):>6} агентов")
        print(f"   Нейтральные           : {counts.get('neutral',  0):>6} агентов")
        print(f"   Хронически позитивные : {counts.get('positive', 0):>6} агентов")

        return df

    # ─────────────────── ШАГ 2: ДИНАМИКА ВОКРУГ ВОСКРЕСЕНИЙ ─────────────────

    def _get_sunday_windows(self, agent_groups: pd.DataFrame) -> pd.DataFrame:
        """
        Для каждого воскресенья извлекает эмоциональный фон агентов
        в окне [-3, +6] дней (3 дня до сброса и 6 дней после).

        SQL: join agent_states с таблицей классификации агентов.
        Тяжёлая группировка остаётся в ClickHouse.
        """
        print("[2/6] Извлечение эмоционального фона вокруг воскресений…")

        emotions_avg = ", ".join([f"avg({e}) AS {e}" for e in EMOTION_AXES])

        # Строим список воскресных дней: 7, 14, 21, ..., 1212
        # Используем modulo в ClickHouse — day_id % 7 = 0
        # Нормируем: offset = day_id - ближайшее_воскресенье
        sql = f"""
            WITH sundays AS (
                -- Список всех воскресений в симуляции
                SELECT DISTINCT
                    intDiv(day_id - 1, {WEEK_LEN}) * {WEEK_LEN} + {WEEK_LEN} AS sunday_day
                FROM agent_states
                WHERE day_id % {WEEK_LEN} = 0
            ),
            windows AS (
                -- Для каждого дня в окне [-3, +6] от воскресенья
                SELECT
                    s.sunday_day,
                    s.sunday_day + offset AS target_day,
                    offset
                FROM sundays s
                CROSS JOIN (
                    SELECT number - 3 AS offset
                    FROM numbers(10)  -- offset: -3..+6
                ) offsets
                WHERE s.sunday_day + offset BETWEEN 1 AND 1212
            )
            SELECT
                w.sunday_day,
                w.offset,
                as2.run_id,
                as2.agent_id,
                ({' + '.join([f'as2.{e}' for e in EMOTION_AXES])}) / 7.0 AS mood_composite,
                {', '.join([f'as2.{e}' for e in EMOTION_AXES])}
            FROM windows w
            JOIN agent_states as2
                ON as2.day_id = w.target_day
            ORDER BY w.sunday_day, w.offset, as2.agent_id
        """
        df_raw = self._q(sql)

        # Подтягиваем группы агентов
        df_classified = agent_groups[["run_id", "agent_id", "group", "baseline_mood"]]
        df_merged = df_raw.merge(df_classified, on=["run_id", "agent_id"], how="inner")

        return df_merged

    # ─────────────────── ШАГ 3: АГРЕГАЦИЯ ПО ГРУППАМ И OFFSET ───────────────

    def _aggregate_recovery(self, df_windows: pd.DataFrame) -> pd.DataFrame:
        """
        Усредняет настроение по группам и offset-дням.
        Нормирует настроение относительно значения в день воскресенья (offset=0).
        """
        print("[3/6] Агрегация кривых восстановления…")

        # Среднее настроение по группам и offset
        df_agg = (
            df_windows.groupby(["group", "offset"])["mood_composite"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
        df_agg.columns = ["group", "offset", "mean_mood", "std_mood", "n"]
        df_agg["se"] = df_agg["std_mood"] / np.sqrt(df_agg["n"])  # стандартная ошибка

        # Нормируем: вычитаем значение при offset=0 (день сброса) для каждой группы
        baseline_at_sunday = (
            df_agg[df_agg["offset"] == 0]
            .set_index("group")["mean_mood"]
        )
        df_agg["mood_delta"] = df_agg.apply(
            lambda r: r["mean_mood"] - baseline_at_sunday.get(r["group"], 0),
            axis=1,
        )

        # Также нормируем: относительное отклонение от предвоскресного базиса (offset=-1)
        baseline_pre = (
            df_agg[df_agg["offset"] == -1]
            .set_index("group")["mean_mood"]
        )
        df_agg["mood_from_pre"] = df_agg.apply(
            lambda r: r["mean_mood"] - baseline_pre.get(r["group"], 0),
            axis=1,
        )

        return df_agg

    # ─────────────────── ШАГ 4: РАСЧЁТ ПЕРИОДА ПОЛУВОССТАНОВЛЕНИЯ ────────────

    def _fit_recovery_curves(
        self, df_agg: pd.DataFrame
    ) -> dict[str, dict]:
        """
        Для каждой группы фитируем экспоненциальное затухание
        на пост-воскресные дни (offset 0..+6).

        Возвращает словарь с параметрами кривой и t½.
        """
        print("[4/6] Аппроксимация кривых восстановления (экспоненциальный fit)…")

        results = {}
        for group in ["negative", "neutral", "positive"]:
            sub = df_agg[(df_agg["group"] == group) & (df_agg["offset"] >= 0)].copy()
            if sub.empty:
                continue

            # Нормируем: максимальный подъём настроения в день 0
            peak = sub[sub["offset"] == 0]["mood_from_pre"].values[0]
            sub["normalized"] = sub["mood_from_pre"] - peak  # убираем пик, смотрим спад

            x = sub["offset"].values.astype(float)
            y = sub["mood_from_pre"].values.astype(float)

            try:
                # Начальные приближения: A = высота пика, λ = 0.3, C = конечный уровень
                A0 = float(peak) if abs(peak) > 0.1 else 1.0
                C0 = float(y[-1])
                p0 = [A0, 0.3, C0]
                popt, pcov = curve_fit(
                    _exponential_decay, x, y,
                    p0=p0, maxfev=5000,
                    bounds=([-30, 0.01, -30], [30, 5.0, 30]),
                )
                A, lam, C = popt
                perr = np.sqrt(np.diag(pcov))
                t_half = _half_recovery_time(A, lam)
                r2 = 1 - np.sum((y - _exponential_decay(x, *popt))**2) / np.sum((y - y.mean())**2)

                results[group] = {
                    "A": A, "lambda": lam, "C": C,
                    "A_err": perr[0], "lambda_err": perr[1],
                    "t_half": t_half,
                    "r2": r2,
                    "peak_delta": peak,
                }
                print(f"   {LABEL[group]:30s}  λ={lam:.3f}  t½={t_half:.2f} дней  R²={r2:.3f}")
            except Exception as e:
                print(f"   ⚠️  Ошибка fit для {group}: {e}")
                results[group] = {"t_half": np.nan, "r2": np.nan, "peak_delta": peak if peak else 0}

        return results

    # ─────────────────── ШАГ 5: ПОСТОЯНСТВО НЕГАТИВНОГО ФОНА ─────────────────

    def _compute_return_persistence(self, df_windows: pd.DataFrame) -> pd.DataFrame:
        """
        Проверяет, возвращается ли настроение к базовому уровню
        через 6 дней после сброса.

        Метрика: mood[offset=+6] - mood[offset=-1]
        Если отрицательное — агент не восстановился полностью.
        """
        print("[5/6] Анализ остаточного эффекта через 6 дней…")

        pre = df_windows[df_windows["offset"] == -1][
            ["run_id", "agent_id", "sunday_day", "group", "mood_composite"]
        ].rename(columns={"mood_composite": "mood_pre"})

        post = df_windows[df_windows["offset"] == 6][
            ["run_id", "agent_id", "sunday_day", "mood_composite"]
        ].rename(columns={"mood_composite": "mood_post"})

        df_pair = pre.merge(post, on=["run_id", "agent_id", "sunday_day"], how="inner")
        df_pair["recovery_gap"] = df_pair["mood_post"] - df_pair["mood_pre"]
        df_pair["fully_recovered"] = df_pair["recovery_gap"] >= 0

        # Доля полностью восстановившихся по группам и неделям
        recovery_rate = (
            df_pair.groupby(["group", "sunday_day"])["fully_recovered"]
            .mean()
            .reset_index()
        )
        recovery_rate.columns = ["group", "sunday_day", "recovery_rate"]

        # Средний gap по группам
        gap_summary = (
            df_pair.groupby("group")["recovery_gap"]
            .agg(["mean", "std", "median"])
            .reset_index()
        )

        return recovery_rate, gap_summary, df_pair

    # ─────────────────── ШАГ 6: ВИЗУАЛИЗАЦИЯ ────────────────────────────────

    def _plot_all(
        self,
        df_agg: pd.DataFrame,
        fit_results: dict,
        recovery_rate: pd.DataFrame,
        gap_summary: pd.DataFrame,
        df_pair: pd.DataFrame,
        df_windows: pd.DataFrame,
        agent_groups: pd.DataFrame,
    ) -> list[str]:
        """Строит 6 графиков."""
        print("[6/6] Визуализация…")
        paths = []

        # ── График 1: Кривые восстановления с экспоненциальным фитом ──────────
        fig, ax = plt.subplots(figsize=(11, 6))
        for group in ["negative", "neutral", "positive"]:
            sub = df_agg[df_agg["group"] == group].sort_values("offset")
            if sub.empty:
                continue
            color = PALETTE[group]
            label = LABEL[group]

            # Данные с доверительным интервалом (95% CI)
            ci = 1.96 * sub["se"]
            ax.fill_between(sub["offset"], sub["mean_mood"] - ci,
                            sub["mean_mood"] + ci,
                            alpha=0.12, color=color)
            ax.plot(sub["offset"], sub["mean_mood"],
                    "o-", color=color, lw=2.2, ms=5, label=label)

            # Экспоненциальный fit (только offset >= 0)
            if group in fit_results and "lambda" in fit_results[group]:
                fr = fit_results[group]
                x_fit = np.linspace(0, 6, 100)
                y_fit = _exponential_decay(x_fit, fr["A"], fr["lambda"], fr["C"])
                ax.plot(x_fit, y_fit, "--", color=color, lw=1.5, alpha=0.7)
                # Аннотация t½
                if np.isfinite(fr["t_half"]):
                    ax.annotate(
                        f"t½ = {fr['t_half']:.1f} д.",
                        xy=(fr["t_half"], _exponential_decay(fr["t_half"], fr["A"], fr["lambda"], fr["C"])),
                        xytext=(fr["t_half"] + 0.3, fr["C"] + (fr["A"] * 0.5)),
                        fontsize=9, color=color,
                        arrowprops=dict(arrowstyle="->", color=color, lw=1.2),
                    )

        ax.axvline(0, color="black", lw=1.5, linestyle=":", label="Воскресный сброс")
        ax.axhline(0, color="grey", lw=0.7, linestyle=":")
        ax.set_title("Кривые восстановления эмоций после воскресного δ-сброса\n"
                     "(среднее по всем 7 осям и по всем воскресеньям симуляции)",
                     fontsize=13, fontweight="bold")
        ax.set_xlabel("Дней до/после воскресного сброса (0 = воскресенье)")
        ax.set_ylabel("Среднее настроение (сводная ось, диапазон [-30, 30])")
        ax.legend(loc="lower right", fontsize=10)
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        paths.append(_savefig(fig, "SR1_recovery_curves"))

        # ── График 2: Нормированный подъём и спад (offset=0 → baseline) ───────
        fig, ax = plt.subplots(figsize=(11, 5))
        for group in ["negative", "neutral", "positive"]:
            sub = df_agg[df_agg["group"] == group].sort_values("offset")
            if sub.empty:
                continue
            ax.plot(sub["offset"], sub["mood_from_pre"],
                    "o-", color=PALETTE[group], lw=2.2, ms=5, label=LABEL[group])
        ax.axvline(0, color="black", lw=1.5, linestyle=":", alpha=0.7)
        ax.axhline(0, color="grey", lw=1, linestyle="--", label="Уровень pre-воскресенья")
        ax.fill_between([-3, 0], [-5, -5], [5, 5], alpha=0.04, color="blue",
                        label="Неделя (до сброса)")
        ax.fill_between([0, 6], [-5, -5], [5, 5], alpha=0.04, color="orange",
                        label="Неделя (после сброса)")
        ax.set_title("Нормированное изменение настроения\n"
                     "(относительно уровня за день до воскресенья)",
                     fontsize=13, fontweight="bold")
        ax.set_xlabel("Дней от воскресного сброса")
        ax.set_ylabel("Δ настроение от pre-базиса")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        paths.append(_savefig(fig, "SR2_normalized_recovery"))

        # ── График 3: Гистограмма t½ по группам ──────────────────────────────
        fig, ax = plt.subplots(figsize=(8, 5))
        groups = ["negative", "neutral", "positive"]
        t_halves = [
            fit_results.get(g, {}).get("t_half", np.nan) for g in groups
        ]
        colors = [PALETTE[g] for g in groups]
        labels = [LABEL[g] for g in groups]
        valid = [(g, t, c, l) for g, t, c, l in zip(groups, t_halves, colors, labels)
                 if np.isfinite(t)]
        if valid:
            gs_, ts_, cs_, ls_ = zip(*valid)
            bars = ax.bar(ls_, ts_, color=cs_, edgecolor="white", linewidth=0.5, width=0.5)
            for bar, t in zip(bars, ts_):
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.05,
                        f"{t:.2f} д.", ha="center", fontsize=12, fontweight="bold")
        ax.set_title("Период полувосстановления (t½) после воскресного δ-сброса",
                     fontsize=13, fontweight="bold")
        ax.set_ylabel("Дней до полувосстановления")
        ax.set_ylim(0, max(ts_) * 1.3 if valid else 5)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        paths.append(_savefig(fig, "SR3_half_recovery_time"))

        # ── График 4: Доля полностью восстановившихся по неделям ─────────────
        fig, ax = plt.subplots(figsize=(13, 5))
        for group in ["negative", "neutral", "positive"]:
            sub = recovery_rate[recovery_rate["group"] == group].sort_values("sunday_day")
            if sub.empty:
                continue
            ax.plot(sub["sunday_day"], sub["recovery_rate"] * 100,
                    color=PALETTE[group], lw=1.5, alpha=0.8, label=LABEL[group])
            # Скользящее среднее
            roll = sub["recovery_rate"].rolling(4, center=True, min_periods=1).mean()
            ax.plot(sub["sunday_day"], roll * 100,
                    color=PALETTE[group], lw=2.5)
        ax.set_title("Доля агентов, полностью восстановившихся за 6 дней после сброса\n"
                     "(тонкая линия — сырые данные, жирная — MA-4 недели)",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("День симуляции (воскресенье)")
        ax.set_ylabel("% полностью восстановившихся")
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.25)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
        fig.tight_layout()
        paths.append(_savefig(fig, "SR4_recovery_rate_dynamics"))

        # ── График 5: Violin plot — recovery_gap по группам ──────────────────
        fig, ax = plt.subplots(figsize=(9, 6))
        data_violin = []
        labels_violin = []
        colors_violin = []
        for group in ["negative", "neutral", "positive"]:
            sub = df_pair[df_pair["group"] == group]["recovery_gap"].dropna()
            if not sub.empty:
                data_violin.append(sub.values)
                labels_violin.append(LABEL[group])
                colors_violin.append(PALETTE[group])

        parts = ax.violinplot(data_violin, positions=range(len(data_violin)),
                              showmedians=True, showextrema=False)
        for pc, color in zip(parts["bodies"], colors_violin):
            pc.set_facecolor(color)
            pc.set_alpha(0.6)
        parts["cmedians"].set_color("black")
        parts["cmedians"].set_linewidth(2)

        # Добавляем box overlay
        ax.boxplot(data_violin, positions=range(len(data_violin)),
                   widths=0.08, patch_artist=False,
                   medianprops=dict(visible=False),
                   whiskerprops=dict(lw=1),
                   capprops=dict(lw=1),
                   flierprops=dict(marker=".", ms=2, alpha=0.3))

        ax.axhline(0, color="red", lw=1.5, linestyle="--", label="Нет изменений (gap=0)")
        ax.set_xticks(range(len(labels_violin)))
        ax.set_xticklabels(labels_violin, fontsize=11)
        ax.set_title("Распределение разрыва восстановления\n"
                     "(mood[+6 дней] − mood[−1 день])",
                     fontsize=13, fontweight="bold")
        ax.set_ylabel("Δ настроение через 6 дней (recovery gap)")
        ax.legend(fontsize=10)
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        paths.append(_savefig(fig, "SR5_recovery_gap_violin"))

        # ── График 6: Тепловая карта — базовый фон по осям и группам ─────────
        fig, ax = plt.subplots(figsize=(10, 4))
        heat_data = []
        heat_labels = []
        for group in ["negative", "neutral", "positive"]:
            row = agent_groups[agent_groups["group"] == group][
                [f"base_{e}" for e in EMOTION_AXES]
            ].mean()
            heat_data.append(row.values)
            heat_labels.append(LABEL[group])
        heat_df = pd.DataFrame(
            heat_data,
            index=heat_labels,
            columns=[EMOTION_LABELS[e] for e in EMOTION_AXES],
        )
        sns.heatmap(
            heat_df, ax=ax,
            cmap="RdYlGn", center=0, vmin=-15, vmax=15,
            annot=True, fmt=".1f", annot_kws={"size": 9},
            linewidths=0.5,
            cbar_kws={"label": "Среднее значение оси"},
        )
        ax.set_title("Профиль базового эмоционального фона по группам агентов",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=30, labelsize=9)
        fig.tight_layout()
        paths.append(_savefig(fig, "SR6_baseline_heatmap"))

        return paths

    # ─────────────────── СТАТИСТИЧЕСКИЕ ТЕСТЫ ────────────────────────────────

    def _statistical_tests(self, df_pair: pd.DataFrame) -> str:
        """
        Проводит статистические тесты различия recovery_gap между группами.
        Возвращает Markdown-таблицу.
        """
        groups = ["negative", "neutral", "positive"]
        data = {
            g: df_pair[df_pair["group"] == g]["recovery_gap"].dropna().values
            for g in groups
        }

        rows = []
        pairs = [
            ("negative", "neutral"),
            ("negative", "positive"),
            ("neutral",  "positive"),
        ]
        for g1, g2 in pairs:
            if len(data[g1]) < 10 or len(data[g2]) < 10:
                continue
            u_stat, p_mw = stats.mannwhitneyu(data[g1], data[g2], alternative="two-sided")
            t_stat, p_t  = stats.ttest_ind(data[g1], data[g2], equal_var=False)
            # Cohen's d
            n1, n2 = len(data[g1]), len(data[g2])
            s_pool = np.sqrt(((n1-1)*data[g1].std()**2 + (n2-1)*data[g2].std()**2) / (n1+n2-2))
            d = (data[g1].mean() - data[g2].mean()) / (s_pool + 1e-9)
            rows.append({
                "Пара": f"{LABEL[g1]} vs {LABEL[g2]}",
                "Mann-Whitney U": f"{u_stat:.0f}",
                "p-value (MW)": f"{p_mw:.4f}",
                "t-stat (Welch)": f"{t_stat:.3f}",
                "p-value (t)": f"{p_t:.4f}",
                "Cohen's d": f"{d:.3f}",
                "Значимо (p<0.05)": "✅" if p_mw < 0.05 else "❌",
            })

        return pd.DataFrame(rows).to_markdown(index=False)

    # ─────────────────── ГЕНЕРАЦИЯ ОТЧЁТА ────────────────────────────────────

    def _save_report(
        self,
        fit_results: dict,
        gap_summary: pd.DataFrame,
        stat_table: str,
        plot_paths: list[str],
    ) -> None:
        """Дописывает раздел в research_report.md."""
        report_path = OUTPUT_DIR / "research_report.md"

        def img(path: str, caption: str) -> str:
            rel = Path(path).relative_to(OUTPUT_DIR.parent)
            return f"\n![{caption}]({rel})\n*{caption}*\n"

        # Интерпретация результатов
        neg_t = fit_results.get("negative", {}).get("t_half", float("nan"))
        neu_t = fit_results.get("neutral",  {}).get("t_half", float("nan"))
        pos_t = fit_results.get("positive", {}).get("t_half", float("nan"))

        if np.isfinite(neg_t) and np.isfinite(neu_t):
            ratio = neg_t / neu_t if neu_t > 0 else float("nan")
            interpretation = (
                f"Хронически негативные агенты восстанавливаются в **{ratio:.2f}×** "
                f"{'медленнее' if ratio > 1 else 'быстрее'}, чем нейтральные "
                f"(t½ = {neg_t:.2f} vs {neu_t:.2f} дней)."
            )
        else:
            interpretation = "Данных недостаточно для однозначного вывода о t½."

        section = textwrap.dedent(f"""

        ## Гипотеза A: «Эффект воскресного сброса» (Sunday Reset Effect)

        ### Постановка

        В модели каждое воскресенье все 7 осей эмоций агента получают единый
        случайный сдвиг δ ∈ [−30, 30] («семейный день»).
        Гипотеза: **агенты с хронически отрицательным фоном восстанавливаются
        медленнее**, так как затухание dE = 0.2 · sᵢ тянет их обратно к нулю
        быстрее, чем у нейтральных, и случайный δ лишь ненадолго поднимает их фон.

        ### Классификация агентов

        | Группа | Порог baseline_mood |
        |--------|---------------------|
        | Хронически негативные | < {CHRONIC_NEGATIVE_THRESHOLD} |
        | Нейтральные | [{CHRONIC_NEGATIVE_THRESHOLD}, {CHRONIC_POSITIVE_THRESHOLD}] |
        | Хронически позитивные | > {CHRONIC_POSITIVE_THRESHOLD} |

        *baseline_mood* = среднее по всем 7 осям за дни 1–6 (до первого сброса).

        ### Результаты аппроксимации (модель: A·e^(−λt) + C)

        | Группа | t½ (дней) | λ | R² |
        |--------|-----------|---|-----|
        | Хронически негативные | {neg_t:.2f} | {fit_results.get('negative', {}).get('lambda', float('nan')):.3f} | {fit_results.get('negative', {}).get('r2', float('nan')):.3f} |
        | Нейтральные           | {neu_t:.2f} | {fit_results.get('neutral',  {}).get('lambda', float('nan')):.3f} | {fit_results.get('neutral',  {}).get('r2', float('nan')):.3f} |
        | Хронически позитивные | {pos_t:.2f} | {fit_results.get('positive', {}).get('lambda', float('nan')):.3f} | {fit_results.get('positive', {}).get('r2', float('nan')):.3f} |

        **Вывод:** {interpretation}

        ### Средний разрыв восстановления (recovery gap = mood[+6] − mood[−1])

        {gap_summary.to_markdown(index=False)}

        ### Статистические тесты (Mann-Whitney U + Welch t-test)

        {stat_table}

        ### Графики

        {img(plot_paths[0], 'SR-1: Кривые восстановления с экспоненциальным фитом и t½')}
        {img(plot_paths[1], 'SR-2: Нормированное изменение настроения (относительно pre-базиса)')}
        {img(plot_paths[2], 'SR-3: Период полувосстановления по группам')}
        {img(plot_paths[3], 'SR-4: Динамика доли полностью восстановившихся по неделям')}
        {img(plot_paths[4], 'SR-5: Violin plot — распределение recovery gap')}
        {img(plot_paths[5], 'SR-6: Тепловая карта базового эмоционального профиля')}
        """)

        with open(report_path, "a", encoding="utf-8") as f:
            f.write(section)
        print(f"\n📝  Раздел дописан в {report_path}")

    # ─────────────────── ПУБЛИЧНАЯ ТОЧКА ВХОДА ───────────────────────────────

    def run(self) -> None:
        print("\n" + "═" * 60)
        print("  SundayResetAnalyzer — Гипотеза «Воскресный сброс»")
        print("═" * 60)

        # 1. Классифицируем агентов по базовому фону
        agent_groups = self._classify_agents()

        # 2. Извлекаем эмоции в окне [-3, +6] от каждого воскресенья
        df_windows = self._get_sunday_windows(agent_groups)

        # 3. Агрегируем по группам
        df_agg = self._aggregate_recovery(df_windows)

        # 4. Фитируем экспоненциальные кривые и считаем t½
        fit_results = self._fit_recovery_curves(df_agg)

        # 5. Анализ остаточного gap через 6 дней
        recovery_rate, gap_summary, df_pair = self._compute_return_persistence(df_windows)

        # 6. Строим все графики
        plot_paths = self._plot_all(
            df_agg, fit_results, recovery_rate, gap_summary, df_pair, df_windows, agent_groups
        )

        # 7. Статтесты
        stat_table = self._statistical_tests(df_pair)

        # 8. Отчёт
        self._save_report(fit_results, gap_summary, stat_table, plot_paths)

        print("\n✅  Анализ завершён.")
        print(f"   Графики: {PLOTS_DIR}")
        print(f"   Отчёт:   {OUTPUT_DIR / 'research_report.md'}")
        print("═" * 60)


# ─────────────────────────────── ТОЧКА ВХОДА ─────────────────────────────────

if __name__ == "__main__":
    analyzer = SundayResetAnalyzer(
        host="localhost",
        port=8123,
        username="default",
        password="clickhouse_pass",
    )
    analyzer.run()
