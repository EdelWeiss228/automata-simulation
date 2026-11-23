"""Единый формат замера времени для сравнения реализаций симулятора.

Python v2 и будущий Rust v3 должны писать одинаковые поля, чтобы можно
было сравнивать скорость на одном сценарии и одном seed. Подробная
запись сохраняется в JSON, краткая — в ClickHouse (если он доступен).

Пример:
    timer = RunTimer("Run01_Erudition_EMPTY", implementation="python-v2")
    ...
    timer.mark("init")
    ...
    timer.mark("simulation")
    timer.finish(status="ok", extra={"agents": 1620, "days": 1213})
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    import resource
except ImportError:  # Windows: замеры памяти/CPU недоступны
    resource = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT_DIR = os.path.join(ROOT, "data", "v2-corrected", "timings")


def _read_version() -> str:
    """Версия исходников: env -> VERSION -> git -> unknown."""
    value = os.getenv("SIM_IMPL_VERSION", "").strip()
    if value:
        return value
    version_file = os.path.join(ROOT, "VERSION")
    try:
        with open(version_file, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
        if value:
            return value
    except OSError:
        pass
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        ).strip() or "unknown"
    except Exception:  # pylint: disable=broad-exception-caught
        return "unknown"


def _max_rss_kb() -> int:
    if resource is None:
        return 0
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # Linux отдаёт килобайты, macOS — байты.
    if sys.platform == "darwin":
        value //= 1024
    return max(0, value)


def _cpu_seconds():
    if resource is None:
        return 0.0, 0.0
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return float(usage.ru_utime), float(usage.ru_stime)


class RunTimer:
    """Таймер одного прогона с фазами и машинно-читаемым результатом."""

    def __init__(self, scenario: str, implementation: str = "python-v2",
                 engine: str = "cpp-openmp", output_dir: str | None = None,
                 seed=None, config_path: str | None = None):
        self.scenario = scenario
        self.implementation = implementation
        self.engine = engine
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        self.seed = seed
        self.config_path = config_path

        self.started_at = datetime.now(timezone.utc)
        self._wall_start = time.perf_counter()
        self._cpu_start = _cpu_seconds()
        self._last_mark = self._wall_start
        self.phases: dict[str, float] = {}
        self._finished = False

    def mark(self, name: str):
        """Закрыть текущую фазу и начать следующую."""
        now = time.perf_counter()
        self.phases[name] = round(now - self._last_mark, 6)
        self._last_mark = now

    def finish(self, status: str = "ok", extra: dict | None = None,
               ch_logger=None) -> dict:
        """Записать результат и вернуть payload.

        Метод не должен ломать симуляцию: любые ошибки логирования
        подавляются, чтобы прогон не падал из-за метрик.
        """
        if self._finished:
            return {}
        self._finished = True

        finished_at = datetime.now(timezone.utc)
        wall = max(0.0, time.perf_counter() - self._wall_start)
        self.phases["finish"] = round(
            max(0.0, time.perf_counter() - self._last_mark), 6)
        cpu_end = _cpu_seconds()
        extra = dict(extra or {})

        payload = {
            "schema": "automata-run-timing/v1",
            "scenario": self.scenario,
            "implementation": self.implementation,
            "engine": self.engine,
            "version": _read_version(),
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "wall_seconds": round(wall, 3),
            "cpu_user_seconds": round(
                max(0.0, cpu_end[0] - self._cpu_start[0]), 3),
            "cpu_system_seconds": round(
                max(0.0, cpu_end[1] - self._cpu_start[1]), 3),
            "max_rss_kb": _max_rss_kb(),
            "phases": self.phases,
            "init_seconds": self.phases.get("init", 0.0),
            "simulation_seconds": self.phases.get("simulation", 0.0),
            "finalize_seconds": self.phases.get("finish", 0.0),
            "status": status,
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "omp_threads": os.getenv("OMP_NUM_THREADS", ""),
            "workers": os.getenv("SIM_WORKERS", ""),
            "pid": os.getpid(),
            "seed": self.seed,
            "config_path": self.config_path,
        }
        payload.update(extra)

        self._write_json(payload)
        if ch_logger is not None:
            try:
                ch_logger.log_run_timing(payload)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        return payload

    def _write_json(self, payload: dict):
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            safe = "".join(
                char if char.isalnum() or char in ("-", "_", ".") else "_"
                for char in self.scenario
            ) or "scenario"
            path = os.path.join(self.output_dir, safe + ".json")
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(tmp, path)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
