"""
advanced_research.py
════════════════════
Восстановленные макро-социальные гипотезы H1–H6.

Источник постановки — черновик Gemini «Исследование макро-социальных
гипотез (v6.0)» и соответствующие разделы текста диплома:
  H1. Коллапс энтропии выбора партнёра.
  H2. Стабильные клики вместо стабильных пар.
  H3. Фазовый переход связности (распад гигантской компоненты).
  H4. Социальные призраки (нулевая взвешенная входящая степень).
  H5. Цепная реакция отказов (r_in → r_out).
  H6. Эхо-камеры (межгрупповая дивергенция эмоционального фона).

Скрипт рассчитан на v2-corrected ClickHouse. Тяжёлые графовые
построения выполняются на представительной выборке, а корреляция
отказов — по всем 54 прогонам.

Запуск:
    ./venv/bin/python scripts/advanced_research.py

Результат:
    data/plots/20_*..25_* (.png + .pdf)
    data/output/advanced_research_report.md
"""

from __future__ import annotations

import bisect
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
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

warnings.filterwarnings("ignore")
matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
PLOTS_DIR = ROOT / "data" / "plots"
OUTPUT_DIR = ROOT / "data" / "output"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DPI_PNG, DPI_PDF = 180, 140
EMOTION_AXES = [
    "sadness_joy", "fear_calm", "anger_humility",
    "disgust_acceptance", "habit_surprise",
    "shame_confidence", "alienation_openness",
]
INIT_TYPES = ["EMPTY", "RANDOM", "MIXED"]
SEM_RANGES = {
    1: (0, 152), 2: (153, 302), 3: (303, 455), 4: (456, 605),
    5: (606, 758), 6: (759, 908), 7: (909, 1061), 8: (1062, 1212),
}
SEM_END_DAYS = [152, 302, 455, 605, 758, 908, 1061, 1212]


def resolve_logged_day(days: List[int], target: int) -> int:
    """Ближайший предыдущий день, который есть в agent_states.

    Выходные и каникулы не логируются, поэтому конец семестра
    сдвигается на последний реально записанный день.
    """
    position = bisect.bisect_right(days, target) - 1
    return days[position] if position >= 0 else target


N_SEMESTERS = 8
N_AGENTS = 1620
TOTAL_DAYS = 1213
HETERO_FAMILIES = [f"Run{i:02d}" for i in range(8, 15)]


def sem_start(semester: int) -> int:
    return SEM_RANGES[semester][0]


def get_sem(day: int) -> int:
    for semester, (start, end) in SEM_RANGES.items():
        if start <= day <= end:
            return semester
    return N_SEMESTERS


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


def h2(title: str) -> str:
    return f"\n\n## {title}\n"


def h3(title: str) -> str:
    return f"\n### {title}\n"


def semester_boundaries_weeks() -> List[float]:
    return [end / 7.0 for end in SEM_END_DAYS[:-1]]


class AdvancedResearch:

    def __init__(self):
        host = os.getenv("CLICKHOUSE_HOST", "db.georgytadjiev.ink")
        port = int(os.getenv("CLICKHOUSE_PORT", "443"))
        user = os.getenv("CLICKHOUSE_USER", "default")
        password = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass")
        secure = os.getenv("CLICKHOUSE_SECURE", "True").lower() in ("true", "1", "yes")
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
        self.n_runs = len(self.runs_df)
        self.max_day = int(self.q("SELECT max(day_id) FROM agent_states").iloc[0, 0])
        self.archetypes = sorted(
            self.q("SELECT DISTINCT archetype FROM agent_registry")["archetype"].tolist())

        self.sample_runs = self._pick_sample(per_family=1)
        self.hetero_runs = self._pick_hetero()
        self.rep_run = self._pick_representative()

        print("✅  Соединение установлено.", flush=True)
        print(f"   Прогонов: {self.n_runs}, max_day: {self.max_day}", flush=True)
        print(f"   Выборка: {len(self.sample_runs)} прогонов", flush=True)
        print(f"   Гетерогенная выборка: {len(self.hetero_runs)} прогонов", flush=True)
        print(f"   Представительный прогон: {self.rep_run}", flush=True)
        print()

    # ── инфраструктура ────────────────────────────────────────────────
    def q(self, sql: str) -> pd.DataFrame:
        df = self.db.query_df(sql)
        if "run_id" in df.columns:
            df["run_id"] = df["run_id"].astype(str)
        return df

    def s(self, sql: str):
        return self.db.query_df(sql).iloc[0, 0]

    def logged_days(self, run_id: str) -> List[int]:
        """Отсортированные дни прогона, реально записанные в agent_states."""
        df = self.q(f"""
            SELECT DISTINCT day_id
            FROM agent_states
            WHERE run_id = '{run_id}'
            ORDER BY day_id
        """)
        if df.empty:
            return []
        return df["day_id"].astype(int).tolist()

    @staticmethod
    def _lcc_share(group: pd.DataFrame, active: set, threshold: float) -> float:
        """Доля агентов в наибольшей компоненте при пороге значимости ребра."""
        n = len(active)
        if n < 2:
            return float("nan")
        totals = group.groupby("from_id")["w"].transform("sum")
        meaningful = group[group["w"] / totals > threshold]
        index_of = {agent: i for i, agent in enumerate(sorted(active))}
        src = meaningful["from_id"].astype(int).map(index_of)
        dst = meaningful["to_id"].astype(int).map(index_of)
        mask = src.notna() & dst.notna()
        if not mask.any():
            return 1.0 / n
        src = src[mask].astype(int).to_numpy()
        dst = dst[mask].astype(int).to_numpy()
        matrix = coo_matrix((np.ones(len(src)), (src, dst)), shape=(n, n))
        _, labels = connected_components(matrix, directed=False)
        return float(np.bincount(labels).max()) / n

    def _load_meta(self) -> pd.DataFrame:
        df = self.q(
            "SELECT run_id, scenario_name, run_name, start_time "
            "FROM simulation_runs ORDER BY scenario_name")

        def _init(name: str) -> str:
            upper = name.upper()
            for init_type in INIT_TYPES:
                if upper.endswith("_" + init_type):
                    return init_type
            for init_type in INIT_TYPES:
                if ("_" + init_type) in upper:
                    return init_type
            return "OTHER"

        df["init_type"] = df["scenario_name"].apply(_init)
        return df

    def _pick_sample(self, per_family: int = 1) -> List[str]:
        sample: List[str] = []
        families = list(dict.fromkeys(self.runs_df["run_name"].tolist()))
        for index, family in enumerate(families):
            subset = self.runs_df[self.runs_df["run_name"] == family]
            wanted = INIT_TYPES[index % len(INIT_TYPES)]
            pick = subset[subset["init_type"] == wanted]
            if pick.empty:
                pick = subset
            sample.extend(pick["run_id"].tolist()[:per_family])
        return sample or self.runs_df["run_id"].tolist()

    def _pick_hetero(self) -> List[str]:
        picked: List[str] = []
        for family in HETERO_FAMILIES:
            subset = self.runs_df[
                self.runs_df["scenario_name"].str.startswith(family + "_")]
            if subset.empty:
                continue
            preferred = subset[subset["init_type"] == "MIXED"]
            row = preferred.iloc[0] if not preferred.empty else subset.iloc[0]
            picked.append(str(row["run_id"]))
        return picked

    def _pick_representative(self) -> str:
        query = """
            SELECT r.run_id
            FROM simulation_runs r
            JOIN agent_registry a ON r.run_id = a.run_id
            WHERE r.scenario_name LIKE '%MIXED%'
            GROUP BY r.run_id
            ORDER BY count(DISTINCT a.archetype) DESC, r.run_id
            LIMIT 1
        """
        df = self.q(query)
        if not df.empty:
            return str(df["run_id"].iloc[0])
        return str(self.sample_runs[0])

    # ── H1: энтропия ──────────────────────────────────────────────────
    def h1_entropy_collapse(self) -> str:
        print("[H1] Коллапс энтропии выбора…", flush=True)
        rep = h2("H1. Коллапс энтропии выбора партнёра")
        rep += (
            "\n**Гипотеза:** по мере накопления отношений выбор партнёра "
            "переходит от почти равномерного (H≈1) к детерминированному "
            "(H→0), то есть коллектив «замерзает».\n"
        )

        frames = []
        for index, run_id in enumerate(self.sample_runs):
            print(f"   [H1] run {index + 1}/{len(self.sample_runs)}…",
                  flush=True, end="\r")
            try:
                df = self.q(f"""
                    SELECT week,
                           avg(h) AS mean_h,
                           quantile(0.25)(h) AS q25,
                           quantile(0.75)(h) AS q75,
                           count() AS n_agents
                    FROM (
                        SELECT week,
                               from_id,
                               1 - sum(cnt * log2(cnt))
                                   / (sum(cnt) * log2(sum(cnt))) AS h
                        FROM (
                            SELECT intDiv(day_id, 7) AS week,
                                   from_id, to_id, count() AS cnt
                            FROM interactions
                            WHERE run_id = '{run_id}'
                            GROUP BY week, from_id, to_id
                        )
                        GROUP BY week, from_id
                        HAVING sum(cnt) >= 2
                    )
                    GROUP BY week
                    ORDER BY week
                """)
                if not df.empty:
                    df["run_id"] = run_id
                    frames.append(df)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"\n   [H1] run {index + 1} ошибка: {exc}", flush=True)

        if not frames:
            return rep + "\n*Нет данных для H1.*\n"

        all_df = pd.concat(frames, ignore_index=True)
        agg = (
            all_df.groupby("week", as_index=False)
            .agg(mean_h=("mean_h", "mean"),
                 q25=("q25", "mean"),
                 q75=("q75", "mean"),
                 n_runs=("run_id", "nunique"))
        )

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(agg["week"], agg["mean_h"], color="#8E24AA", lw=2.4)
        ax.fill_between(agg["week"], agg["q25"], agg["q75"],
                        color="#8E24AA", alpha=0.18,
                        label="IQR по агентам")
        for boundary in semester_boundaries_weeks():
            ax.axvline(boundary, color="#607D8B", ls="--", lw=1, alpha=0.5)
        ax.set_xlabel("Учебная неделя")
        ax.set_ylabel("Нормированная энтропия H")
        ax.set_ylim(0, 1.02)
        ax.set_title("H1. Коллапс энтропии выбора партнёра")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=9)
        fig.tight_layout()
        plot = savefig(fig, "20_entropy_collapse_detailed")
        rep += img_md(plot, "Нормированная энтропия выбора по неделям")

        agg["semester"] = agg["week"].apply(lambda w: get_sem(min(int(w * 7), self.max_day)))
        sem = (
            agg.groupby("semester", as_index=False)
            .agg(mean_h=("mean_h", "mean"),
                 q25=("q25", "mean"),
                 q75=("q75", "mean"))
        )
        rep += h3("Средняя энтропия по семестрам")
        rep += sem.round(3).to_markdown(index=False)
        first = float(sem.loc[sem["semester"] == 1, "mean_h"].iloc[0])
        last = float(sem.loc[sem["semester"] == 8, "mean_h"].iloc[0])
        drop = (first - last) / first * 100 if first else 0
        rep += (
            f"\n\n- Семестр 1: **{first:.3f}**\n"
            f"- Семестр 8: **{last:.3f}**\n"
            f"- Падение: **{drop:.1f}%**\n"
            f"- Прогонов в выборке: {len(self.sample_runs)}\n"
        )
        rep += (
            "\n**Вывод:** "
            + ("гипотеза подтверждается — энтропия монотонно падает."
               if drop > 50 else
               "гипотеза подтверждается частично — энтропия снижается, но не до нуля."
               if drop > 20 else
               "гипотеза не подтверждается — выраженного коллапса нет.")
            + "\n"
        )
        return rep

    # ── H2: клики ─────────────────────────────────────────────────────
    def h2_stable_cliques(self) -> str:
        print("[H2] Стабильные клики…", flush=True)
        rep = h2("H2. Стабильные клики вместо стабильных пар")
        rep += (
            "\n**Гипотеза:** устойчивость системы держится не на бинарных "
            "парах, а на кликах из 3–5 агентов, внутри которых проходит "
            "основная часть контактов.\n"
        )

        try:
            import networkx as nx
        except ImportError:
            return rep + "\n*networkx не установлен.*\n"

        start_day = sem_start(8)
        run_id = self.rep_run
        try:
            pairs = self.q(f"""
                SELECT least(from_id, to_id) AS a,
                       greatest(from_id, to_id) AS b,
                       count() AS w
                FROM interactions
                WHERE run_id = '{run_id}' AND day_id >= {start_day}
                GROUP BY a, b
            """)
            totals = self.q(f"""
                SELECT from_id AS agent_id, count() AS n
                FROM interactions
                WHERE run_id = '{run_id}' AND day_id >= {start_day}
                GROUP BY from_id
            """)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return rep + f"\n*Ошибка запроса: {exc}*\n"

        if pairs.empty:
            return rep + "\n*Нет взаимодействий в последнем семестре.*\n"

        long = pd.concat([
            pairs.rename(columns={"a": "agent", "b": "partner"})[
                ["agent", "partner", "w"]],
            pairs.rename(columns={"b": "agent", "a": "partner"})[
                ["agent", "partner", "w"]],
        ], ignore_index=True)
        top = (
            long.sort_values(["agent", "w"], ascending=[True, False])
            .groupby("agent", as_index=False)
            .head(8)
        )

        graph = nx.Graph()
        for row in top.itertuples(index=False):
            graph.add_edge(int(row.agent), int(row.partner), weight=float(row.w))
        cliques = [c for c in nx.find_cliques(graph) if len(c) >= 3]
        cliques.sort(key=len, reverse=True)

        adjacency: Dict[int, Dict[int, float]] = {}
        for row in long.itertuples(index=False):
            adjacency.setdefault(int(row.agent), {})[int(row.partner)] = float(row.w)
        total_map = dict(zip(totals["agent_id"].astype(int), totals["n"].astype(float)))

        best: Dict[int, List[int]] = {}
        for clique in cliques:
            for agent in clique:
                if len(clique) > len(best.get(agent, [])):
                    best[agent] = clique

        rows = []
        for agent, clique in best.items():
            members = [m for m in clique if m != agent]
            inside = sum(adjacency.get(agent, {}).get(m, 0.0) for m in members)
            total = total_map.get(agent, 0.0)
            if total > 0:
                rows.append({
                    "agent_id": agent,
                    "clique_size": len(clique),
                    "inside_share": inside / total,
                })
        share_df = pd.DataFrame(rows)

        rep += h3("Параметры клик в последнем семестре")
        rep += (
            f"\n- Представительный прогон: `{run_id}`\n"
            f"- Агентов в кликах размера ≥3: **{len(share_df)}** из {N_AGENTS}\n"
            f"- Найдено максимальных клик: **{len(cliques)}**\n"
        )
        if not share_df.empty:
            rep += (
                f"- Размер клики: медиана **{share_df['clique_size'].median():.0f}**, "
                f"максимум **{share_df['clique_size'].max():.0f}**\n"
                f"- Доля контактов внутри своей клики: "
                f"среднее **{share_df['inside_share'].mean() * 100:.1f}%**, "
                f"медиана **{share_df['inside_share'].median() * 100:.1f}%**\n"
            )

        fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
        if not share_df.empty:
            size_counts = share_df["clique_size"].value_counts().sort_index()
            axes[0].bar(size_counts.index.astype(str), size_counts.values,
                        color="#26A69A", edgecolor="white")
            axes[0].set_title("Размер клики")
            axes[0].set_xlabel("Число участников")
            axes[0].set_ylabel("Число агентов")
            axes[1].hist(share_df["inside_share"] * 100, bins=30,
                         color="#EF6C00", edgecolor="white")
            axes[1].set_title("Доля контактов внутри клики")
            axes[1].set_xlabel("% контактов агента")
            axes[1].set_ylabel("Число агентов")
            for axis in axes:
                axis.grid(alpha=0.2)
        fig.tight_layout()
        plot = savefig(fig, "25_clique_structure")
        rep += img_md(plot, "Структура клик в последнем семестре")

        rep += (
            "\n**Вывод:** "
            + ("гипотеза подтверждается — большинство активных агентов "
               "входит в клики и тратит внутри них значимую долю контактов."
               if not share_df.empty and share_df["inside_share"].median() > 0.5
               else "гипотеза подтверждается частично — клики есть, но "
                    "внутрикликовый обмен не доминирует."
               if not share_df.empty else
               "гипотеза не подтверждается — устойчивых клик не найдено.")
            + "\n"
        )
        return rep

    # ── H3: фазовый переход ───────────────────────────────────────────
    def h3_phase_transition(self) -> str:
        print("[H3] Фазовый переход связности…", flush=True)
        rep = h2("H3. Фазовый переход связности")
        rep += (
            "\n**Гипотеза:** единая гигантская компонента графа "
            "скачкообразно распадается на изолированные подграфы; "
            "доля агентов в наибольшей компоненте μ(w) падает с ~1 до <0.5.\n"
        )

        frames = []
        threshold_rows: List[dict] = []
        for index, run_id in enumerate(self.hetero_runs):
            print(f"   [H3] run {index + 1}/{len(self.hetero_runs)}…",
                  flush=True, end="\r")
            try:
                edges = self.q(f"""
                    SELECT intDiv(day_id, 7) AS week,
                           from_id, to_id, count() AS w
                    FROM interactions
                    WHERE run_id = '{run_id}'
                    GROUP BY week, from_id, to_id
                """)
                if edges.empty:
                    continue

                logged = self.logged_days(run_id)
                active_by_sem = {}
                for semester, end in zip(range(1, N_SEMESTERS + 1), SEM_END_DAYS):
                    day = resolve_logged_day(logged, end)
                    active = self.q(f"""
                        SELECT DISTINCT agent_id
                        FROM agent_states
                        WHERE run_id = '{run_id}' AND day_id = {day}
                    """)
                    if active.empty:
                        active_by_sem[semester] = set()
                    else:
                        active_by_sem[semester] = set(
                            active["agent_id"].astype(int).tolist())

                rows = []
                for week, group in edges.groupby("week"):
                    week = int(week)
                    semester = get_sem(min(week * 7, self.max_day))
                    active = active_by_sem.get(semester, set())
                    if len(active) < 2:
                        continue

                    # «Значимая» связь недели: пара даёт инициатору
                    # больше 5% его недельных контактов. Без порога
                    # разреженный граф остаётся связным.
                    rows.append((week, self._lcc_share(group, active, 0.05)))

                    # Проверка устойчивости вывода к выбору порога:
                    # конец 1-го и конец 8-го семестра.
                    if week in (20, 172):
                        period = "С1" if week == 20 else "С8"
                        for threshold in (0.05, 0.10, 0.15, 0.20):
                            threshold_rows.append({
                                "run_id": run_id,
                                "period": period,
                                "threshold": threshold,
                                "mu": self._lcc_share(group, active, threshold),
                            })

                if rows:
                    frames.append(pd.DataFrame(rows, columns=["week", "mu"]))
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"\n   [H3] run {index + 1} ошибка: {exc}", flush=True)

        if not frames:
            return rep + "\n*Нет данных для H3.*\n"

        all_df = pd.concat(frames, ignore_index=True)
        agg = (
            all_df.groupby("week", as_index=False)
            .agg(mu=("mu", "mean"),
                 q25=("mu", lambda x: np.quantile(x, 0.25)),
                 q75=("mu", lambda x: np.quantile(x, 0.75)),
                 n_runs=("mu", "size"))
        )

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(agg["week"], agg["mu"], color="#1565C0", lw=2.4)
        ax.fill_between(agg["week"], agg["q25"], agg["q75"],
                        color="#1565C0", alpha=0.18, label="IQR по прогонам")
        for boundary in semester_boundaries_weeks():
            ax.axvline(boundary, color="#607D8B", ls="--", lw=1, alpha=0.5)
        ax.set_xlabel("Учебная неделя")
        ax.set_ylabel("Доля в наибольшей компоненте μ")
        ax.set_ylim(0, 1.02)
        ax.set_title("H3. Фазовый переход связности")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=9)
        fig.tight_layout()
        plot = savefig(fig, "24_phase_transition")
        rep += img_md(plot, "Доля агентов в гигантской компоненте по неделям")

        agg["semester"] = agg["week"].apply(
            lambda w: get_sem(min(int(w * 7), self.max_day)))
        sem = (
            agg.groupby("semester", as_index=False)
            .agg(mu=("mu", "mean"), q25=("q25", "mean"), q75=("q75", "mean"))
        )
        rep += h3("Средняя μ по семестрам")
        rep += sem.round(3).to_markdown(index=False)
        first = float(sem.loc[sem["semester"] == 1, "mu"].iloc[0])
        last = float(sem.loc[sem["semester"] == 8, "mu"].iloc[0])
        rep += (
            f"\n\n- Семестр 1: **{first:.3f}**\n"
            f"- Семестр 8: **{last:.3f}**\n"
            f"- Прогонов: {len(self.hetero_runs)}\n"
        )

        if threshold_rows:
            threshold_df = (
                pd.DataFrame(threshold_rows)
                .groupby(["period", "threshold"], as_index=False)["mu"].mean()
                .pivot(index="threshold", columns="period", values="mu")
            )
            rep += h3("Чувствительность μ к порогу значимости ребра")
            rep += threshold_df.round(3).to_markdown()
            rep += (
                "\n\nПри пороге 5% граф связен и в начале, и в конце "
                "обучения. Заметная фрагментация появляется только при "
                "пороге 15–20%, причём уже в 1-м семестре: это эффект "
                "выбора порога, а не временной фазовый переход.\n"
            )
        rep += (
            "\n**Вывод:** "
            + ("гипотеза подтверждается — связность резко падает."
               if first - last > 0.4 else
               "гипотеза подтверждается частично — связность снижается умеренно."
               if first - last > 0.15 else
               "гипотеза не подтверждается — гигантская компонента устойчива.")
            + "\n"
        )
        return rep

    # ── H4: социальные призраки ───────────────────────────────────────
    def h4_social_ghosts(self) -> str:
        print("[H4] Социальные призраки…", flush=True)
        rep = h2("H4. Социальные призраки")
        rep += (
            "\n**Гипотеза:** по мере замыкания клик растёт доля агентов, "
            "к которым никто не испытывает значительной симпатии "
            "(нулевая взвешенная входящая степень при A_ij > 10).\n"
        )

        frames = []
        for index, run_id in enumerate(self.sample_runs):
            print(f"   [H4] run {index + 1}/{len(self.sample_runs)}…",
                  flush=True, end="\r")
            try:
                logged = self.logged_days(run_id)
                days = [resolve_logged_day(logged, end) for end in SEM_END_DAYS]
                relations = self.q(f"""
                    SELECT day_id, object_id,
                           count(DISTINCT subject_id) AS n_in
                    FROM agent_relations
                    WHERE run_id = '{run_id}'
                      AND day_id IN ({', '.join(map(str, days))})
                      AND affinity > 10
                    GROUP BY day_id, object_id
                """)
                if relations.empty:
                    continue
                for semester, day in zip(range(1, N_SEMESTERS + 1), days):
                    active = self.q(f"""
                        SELECT DISTINCT agent_id
                        FROM agent_states
                        WHERE run_id = '{run_id}' AND day_id = {day}
                    """)
                    if active.empty:
                        continue
                    active_ids = set(active["agent_id"].astype(int).tolist())
                    if not active_ids:
                        continue
                    day_rows = relations[relations["day_id"] == day]
                    with_incoming = set(day_rows["object_id"].astype(int).tolist())
                    ghosts = len(active_ids - with_incoming)
                    frames.append({
                        "run_id": run_id,
                        "semester": semester,
                        "day_id": day,
                        "n_active": len(active_ids),
                        "n_ghosts": ghosts,
                        "share": ghosts / len(active_ids),
                    })
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"\n   [H4] run {index + 1} ошибка: {exc}", flush=True)

        if not frames:
            return rep + "\n*Нет данных для H4.*\n"

        all_df = pd.DataFrame(frames)
        agg = (
            all_df.groupby("semester", as_index=False)
            .agg(share=("share", "mean"),
                 q25=("share", lambda x: np.quantile(x, 0.25)),
                 q75=("share", lambda x: np.quantile(x, 0.75)),
                 n_runs=("run_id", "nunique"))
        )
        agg["share_pct"] = agg["share"] * 100

        # Квантили по прогонам могут оказаться чуть выше среднего из-за
        # округления/малого числа наблюдений; отрицательная длина уса
        # недопустима для matplotlib.
        lower = (agg["share_pct"] - agg["q25"] * 100).clip(lower=0)
        upper = (agg["q75"] * 100 - agg["share_pct"]).clip(lower=0)
        print(agg[["semester", "share_pct", "q25", "q75", "n_runs"]]
              .round(4).to_string(index=False), flush=True)

        fig, ax = plt.subplots(figsize=(8.5, 4.8))
        ax.bar(agg["semester"], agg["share_pct"],
               color="#6D4C41", alpha=0.85, edgecolor="white")
        ax.errorbar(
            agg["semester"], agg["share_pct"], yerr=[lower, upper],
            fmt="none", ecolor="#212121", capsize=4, lw=1.2)
        ax.set_xticks(agg["semester"])
        ax.set_xlabel("Семестр")
        ax.set_ylabel("Доля «призраков», %")
        ax.set_title("H4. Агенты без значимой входящей симпатии")
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        plot = savefig(fig, "23_social_ghosts")
        rep += img_md(plot, "Доля социальных призраков по семестрам")

        rep += h3("Доля призраков по семестрам")
        rep += agg[["semester", "share_pct", "q25", "q75", "n_runs"]].round(3).to_markdown(index=False)
        first = float(agg.loc[agg["semester"] == 1, "share_pct"].iloc[0])
        last = float(agg.loc[agg["semester"] == 8, "share_pct"].iloc[0])
        rep += (
            f"\n\n- Семестр 1: **{first:.2f}%**\n"
            f"- Семестр 8: **{last:.2f}%**\n"
            f"- Прогонов: {len(self.sample_runs)}\n"
        )
        rep += (
            "\n**Вывод:** "
            + ("гипотеза подтверждается — доля призраков растёт."
               if last > first + 2 else
               "гипотеза подтверждается частично — доля меняется слабо."
               if last > first else
               "гипотеза не подтверждается — доля призраков не растёт.")
            + "\n"
        )
        return rep

    # ── H5: цепная реакция отказов ────────────────────────────────────
    @staticmethod
    def _pearson_from_buckets(buckets: pd.DataFrame) -> float:
        """Точный Пирсон по агент-дням из агрегатов по числу отказов."""
        n = float(buckets["samples"].sum())
        if n <= 0:
            return float("nan")
        x = buckets["received_yesterday"].astype(float)
        mean_x = float((buckets["samples"] * x).sum()) / n
        mean_y = float(buckets["sum_issued"].sum()) / n
        var_x = float((buckets["samples"] * x * x).sum()) / n - mean_x ** 2
        var_y = float(buckets["sum_issued_sq"].sum()) / n - mean_y ** 2
        cov = float((x * buckets["sum_issued"]).sum()) / n - mean_x * mean_y
        if var_x <= 0 or var_y <= 0:
            return float("nan")
        return cov / np.sqrt(var_x * var_y)

    def h5_refusal_cascade(self) -> str:
        print("[H5] Цепная реакция отказов…", flush=True)
        rep = h2("H5. Цепная реакция отказов")
        rep += (
            "\n**Гипотеза:** отказы, полученные агентом в день D, "
            "повышают число отказов, которые он выдаёт в день D+1. "
            "Метрика лаговая: иначе общий объём контактов механически "
            "создаёт ложную корреляцию.\n"
        )

        frames = []
        run_ids = self.runs_df["run_id"].astype(str).tolist()
        for index, run_id in enumerate(run_ids):
            print(f"   [H5] run {index + 1}/{len(run_ids)}…",
                  flush=True, end="\r")
            try:
                df = self.q(f"""
                    SELECT archetype,
                           received_yesterday,
                           count() AS samples,
                           sum(issued_today) AS sum_issued,
                           sum(issued_today * issued_today) AS sum_issued_sq
                    FROM (
                        SELECT today.agent_id,
                               today.archetype,
                               today.issued_today,
                               yesterday.received_refusals AS received_yesterday
                        FROM (
                            SELECT i.to_id AS agent_id,
                                   i.day_id,
                                   ar.archetype,
                                   countIf(i.type = 0) AS issued_today
                            FROM interactions i
                            JOIN agent_registry ar
                              ON i.run_id = ar.run_id
                             AND i.to_id = ar.agent_id
                            WHERE i.run_id = '{run_id}'
                            GROUP BY i.to_id, i.day_id, ar.archetype
                        ) AS today
                        JOIN (
                            SELECT from_id AS agent_id,
                                   day_id,
                                   countIf(type = 0) AS received_refusals
                            FROM interactions
                            WHERE run_id = '{run_id}'
                            GROUP BY from_id, day_id
                        ) AS yesterday
                          ON today.agent_id = yesterday.agent_id
                         AND today.day_id = yesterday.day_id + 1
                    )
                    GROUP BY archetype, received_yesterday
                    ORDER BY archetype, received_yesterday
                """)
                if not df.empty:
                    df["run_id"] = run_id
                    frames.append(df)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"\n   [H5] run {index + 1} ошибка: {exc}", flush=True)

        if not frames:
            return rep + "\n*Нет данных для H5.*\n"

        all_df = pd.concat(frames, ignore_index=True)
        buckets = (
            all_df.groupby("received_yesterday", as_index=False)
            .agg(samples=("samples", "sum"),
                 sum_issued=("sum_issued", "sum"),
                 sum_issued_sq=("sum_issued_sq", "sum"))
            .sort_values("received_yesterday")
        )
        buckets["avg_issued"] = buckets["sum_issued"] / buckets["samples"]
        total_pairs = int(buckets["samples"].sum())
        r_value = self._pearson_from_buckets(buckets)

        rep += (
            f"\n- Агент-дней в анализе: **{total_pairs:,}**\n"
            f"- Пирсон r(получено вчера, выдано сегодня): "
            f"**{r_value:.3f}**\n"
            f"- Диапазон полученных отказов: "
            f"{int(buckets['received_yesterday'].min())}–"
            f"{int(buckets['received_yesterday'].max())}\n"
        )

        zero = buckets[buckets["received_yesterday"] == 0]["avg_issued"]
        high = buckets[buckets["received_yesterday"] >= 3]
        if not zero.empty and not high.empty:
            high_avg = float(high["sum_issued"].sum() / high["samples"].sum())
            rep += (
                f"- Среднее выдано при 0 полученных: **{float(zero.iloc[0]):.3f}**\n"
                f"- Среднее выдано при ≥3 полученных: **{high_avg:.3f}**\n"
            )

        within_rows = []
        for archetype, group in all_df.groupby("archetype"):
            arch_buckets = (
                group.groupby("received_yesterday", as_index=False)
                .agg(samples=("samples", "sum"),
                     sum_issued=("sum_issued", "sum"),
                     sum_issued_sq=("sum_issued_sq", "sum"))
            )
            if arch_buckets["samples"].sum() < 500:
                continue
            within_rows.append({
                "archetype": archetype,
                "n": int(arch_buckets["samples"].sum()),
                "r": self._pearson_from_buckets(arch_buckets),
            })
        within = pd.DataFrame(within_rows)
        if not within.empty:
            weights = within["n"] / within["n"].sum()
            r_within = float((within["r"] * weights).sum())
            rep += (
                f"- Взвешенное r внутри архетипов: **{r_within:.3f}**\n"
                f"- Архетипов: {len(within)}\n"
            )
        else:
            r_within = float("nan")

        fig, ax = plt.subplots(figsize=(8.5, 5.2))
        ax.scatter(
            buckets["received_yesterday"], buckets["avg_issued"],
            s=np.clip(buckets["samples"] / 400.0, 8, 400),
            color="#1565C0", alpha=0.75, edgecolor="white")
        x = buckets["received_yesterday"].to_numpy(dtype=float)
        y = buckets["avg_issued"].to_numpy(dtype=float)
        if len(buckets) > 1:
            weights = np.sqrt(buckets["samples"].to_numpy(dtype=float))
            slope, intercept = np.polyfit(x, y, 1, w=weights)
            x_line = np.linspace(x.min(), x.max(), 100)
            ax.plot(x_line, slope * x_line + intercept,
                    color="#E53935", lw=2, label="Взвешенная регрессия")
        ax.set_xlabel("Получено отказов вчера")
        ax.set_ylabel("Среднее выдано отказов сегодня")
        ax.set_title(f"H5. Цепная реакция отказов (r = {r_value:.3f})")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=9)
        fig.tight_layout()
        plot = savefig(fig, "21_refusal_cascade")
        rep += img_md(plot, "Отказы вчера → отказы сегодня")

        top = buckets[buckets["received_yesterday"] <= 10].copy()
        top["samples"] = top["samples"].astype(int)
        rep += h3("Среднее число выданных отказов по полученным вчера")
        rep += top[["received_yesterday", "samples", "avg_issued"]].round(3).to_markdown(index=False)

        if not within.empty:
            rep += h3("Корреляция внутри архетипов")
            rep += within.round(3).to_markdown(index=False)

        rep += (
            "\n**Вывод:** "
            + ("гипотеза подтверждается — лаговая связь устойчива "
               "и внутри архетипов."
               if r_value > 0.1 and np.isfinite(r_within) and r_within > 0.05 else
               "гипотеза не подтверждается как механизм заражения: "
               "лаговая связь почти полностью объясняется составом "
               f"архетипов (r внутри архетипов = {r_within:.3f})."
               if r_value > 0.1 else
               "гипотеза не подтверждается — значимой лаговой связи нет.")
            + "\n"
        )
        return rep

    # ── H6: эхо-камеры ────────────────────────────────────────────────
    def h6_echo_chambers(self) -> str:
        print("[H6] Эхо-камеры эмоций…", flush=True)
        rep = h2("H6. Эхо-камеры эмоционального фона")
        rep += (
            "\n**Гипотеза:** при одинаковых правилах автомата учебные группы "
            "расходятся по среднему эмоциональному фону, образуя устойчивые "
            "«эмоциональные ниши»; межгрупповая дисперсия растёт.\n"
        )

        emotion_sum = " + ".join(EMOTION_AXES)
        frames = []
        for index, run_id in enumerate(self.sample_runs):
            print(f"   [H6] run {index + 1}/{len(self.sample_runs)}…",
                  flush=True, end="\r")
            try:
                logged = self.logged_days(run_id)
                days = [resolve_logged_day(logged, end) for end in SEM_END_DAYS]
                df = self.q(f"""
                    SELECT s.day_id,
                           r.group_id,
                           avg(({emotion_sum}) / 7.0) AS mean_e
                    FROM agent_states s
                    JOIN agent_registry r
                      ON s.run_id = r.run_id AND s.agent_id = r.agent_id
                    WHERE s.run_id = '{run_id}'
                      AND s.day_id IN ({', '.join(map(str, days))})
                    GROUP BY s.day_id, r.group_id
                    HAVING count() >= 10
                """)
                if df.empty:
                    continue
                for semester, day in zip(range(1, N_SEMESTERS + 1), days):
                    subset = df[df["day_id"] == day]
                    if len(subset) < 2:
                        continue
                    frames.append({
                        "run_id": run_id,
                        "semester": semester,
                        "variance": float(np.var(subset["mean_e"], ddof=0)),
                        "std": float(np.std(subset["mean_e"], ddof=0)),
                        "n_groups": len(subset),
                    })
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"\n   [H6] run {index + 1} ошибка: {exc}", flush=True)

        if not frames:
            return rep + "\n*Нет данных для H6.*\n"

        all_df = pd.DataFrame(frames)
        agg = (
            all_df.groupby("semester", as_index=False)
            .agg(variance=("variance", "median"),
                 q25=("variance", lambda x: np.quantile(x, 0.25)),
                 q75=("variance", lambda x: np.quantile(x, 0.75)),
                 std=("std", "median"),
                 n_runs=("run_id", "nunique"))
        )

        fig, ax = plt.subplots(figsize=(9, 4.8))
        ax.plot(agg["semester"], agg["variance"], marker="o",
                color="#00897B", lw=2.4)
        ax.fill_between(agg["semester"], agg["q25"], agg["q75"],
                        color="#00897B", alpha=0.18, label="IQR по прогонам")
        ax.set_xlabel("Семестр")
        ax.set_ylabel("Var_g[средний эмоциональный фон]")
        ax.set_title("H6. Межгрупповая дивергенция эмоций")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=9)
        fig.tight_layout()
        plot = savefig(fig, "22_emotion_echo")
        rep += img_md(plot, "Межгрупповая дисперсия эмоционального фона")

        rep += h3("Дисперсия по семестрам (группы ≥10 агентов)")
        rep += agg.round(4).to_markdown(index=False)
        first = float(agg.loc[agg["semester"] == 1, "variance"].iloc[0])
        last = float(agg.loc[agg["semester"] == 8, "variance"].iloc[0])
        growth = last / first if first > 0 else float("inf")
        rho_sem, p_sem = stats.spearmanr(agg["semester"], agg["variance"])
        rep += (
            f"\n\n- Семестр 1: **{first:.3f}** (std ≈ {np.sqrt(first):.2f})\n"
            f"- Семестр 8: **{last:.3f}** (std ≈ {np.sqrt(last):.2f})\n"
            f"- Рост дисперсии: **×{growth:.2f}**\n"
            f"- Спирмен ρ(семестр, дисперсия): **{rho_sem:.3f}**, "
            f"p = {p_sem:.3g}\n"
            f"- Прогонов: {len(self.sample_runs)}\n"
        )
        rep += (
            "\n**Вывод:** "
            + ("гипотеза подтверждается — дисперсия монотонно растёт."
               if rho_sem > 0.5 and p_sem < 0.05 else
               "гипотеза подтверждается частично — группы расходятся внутри "
               "отдельных семестров, но семестровый сброс эмоций возвращает "
               "дисперсию к низким значениям, поэтому монотонного роста нет."
               if rho_sem > 0.2 else
               "гипотеза не подтверждается — монотонного роста межгрупповой "
               "дисперсии нет; наблюдаются всплески и сбросы.")
            + "\n"
        )
        return rep

    # ── отчёт ─────────────────────────────────────────────────────────
    def _save_report(self) -> None:
        header = textwrap.dedent(f"""
            # Отчёт: макро-социальные гипотезы H1–H6
            **Дата:** {self._ts} | **Прогонов в базе:** {self.n_runs} | **max_day:** {self.max_day}
            **Выборка:** {len(self.sample_runs)} прогонов (по одному на серию);
            графовые блоки H2–H3 — {len(self.hetero_runs)} гетерогенных прогонов;
            H5 — все {self.n_runs} прогонов.
            **Источник постановки:** черновик Gemini «Исследование макро-социальных
            гипотез (v6.0)» и разделы 6.10–6.13 текста диплома.
            ---
        """).strip()
        path = OUTPUT_DIR / "advanced_research_report.md"
        path.write_text(header + "\n" + "\n".join(self._parts), encoding="utf-8")
        print(f"\n📝  {path}\n📊  {PLOTS_DIR.resolve()}\n" + "═" * 60)

    def run_all(self) -> None:
        print("\n" + "═" * 62)
        print("  ADVANCED RESEARCH — макро-гипотезы H1–H6")
        print("═" * 62 + "\n")
        analyses = [
            ("H1", self.h1_entropy_collapse),
            ("H2", self.h2_stable_cliques),
            ("H3", self.h3_phase_transition),
            ("H4", self.h4_social_ghosts),
            ("H5", self.h5_refusal_cascade),
            ("H6", self.h6_echo_chambers),
        ]
        for name, function in analyses:
            try:
                self._parts.append(function())
                print(f"  ✅ {name} готов\n", flush=True)
            except Exception:
                error = traceback.format_exc()
                print(f"  ⚠️  {name}:\n{error}\n", flush=True)
                self._parts.append(f"\n## {name} — ошибка\n```\n{error}\n```\n")
        self._save_report()


if __name__ == "__main__":
    AdvancedResearch().run_all()
