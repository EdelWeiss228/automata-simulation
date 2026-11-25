"""Единый Telegram-бот наблюдения за матричным прогоном v2-corrected.

Совмещает автоматические отчёты наблюдателя и кнопки старого бота:
статус, прогресс, ресурсы сервера, логи, перезапуск и остановка.

Бот не обязателен для симуляции: он только читает batch.log, batch.pid,
каталог done/ и ClickHouse. Если токена нет, скрипт завершится с понятным
сообщением и не затронет работающий прогон.

Запуск:
    ./venv/bin/python scripts/tg_batch_watcher.py

Токен и chat_id берутся из .env:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...
"""

import glob
import html
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_ROOT = os.path.join(ROOT, "data", "v2-corrected")
BATCH_LOG = os.path.join(OUTPUT_ROOT, "batch.log")
PID_FILE = os.path.join(OUTPUT_ROOT, "batch.pid")
DONE_DIR = os.path.join(OUTPUT_ROOT, "done")
LOGS_DIR = os.path.join(OUTPUT_ROOT, "logs")
EXTERNAL_DISK = "/run/media/georgiy/home_external"
SERVICE = "automata-batch.service"

# Логи анализаторов лежат рядом с batch.log, но называются по-разному:
# analysis_*.out, mega_*.out, hypotheses_*.out, sunday_*.out и т.п.
ANALYZER_LOG_GLOBS = (
    "analysis*.out", "mega_*.out", "hypotheses_*.out",
    "sunday_*.out", "baseline_*.out", "research_*.out",
    "advanced_*.out",
)
ANALYZER_SCRIPTS = (
    "mega_research.py", "hypotheses_9.py", "baseline_9.py",
    "research_analyzer.py", "sunday_reset_analysis.py",
    "advanced_research.py", "run_v2_analysis.py",
)

TOTAL_SCENARIOS = 54
# 1213 = 4 учебных года: 153 дня осенью + 150 весной (весна 2028 — 151
# из-за 29 февраля). Июль и август не симулируются. В ClickHouse
# day_id 0..1212, поэтому в сообщениях показываем день на единицу больше.
TOTAL_DAYS = 1213
UPDATE_EVERY = timedelta(minutes=30)
POLL_TIMEOUT = 25
SIM_START_DATE = date(2024, 9, 1)

RUNNING = threading.Event()
RUNNING.set()

WELCOME = (
    "<b>Бот мониторинга v2-corrected</b>\n"
    "Кнопки: статус, прогресс, ресурсы, логи воркеров, логи анализаторов,\n"
    "перезапуск и остановка (с подтверждением).\n"
    "Команды: /status /progress /resources /logs /analysis_logs "
    "/restart /stop /clean_restart"
)


def log(message):
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


# ---------------------------------------------------------------------------
# Telegram API
# ---------------------------------------------------------------------------

def load_env_file(path):
    """Минимальный парсер .env без внешних зависимостей."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value


def api_call(token, method, payload=None, timeout=35):
    """Вызвать метод Telegram Bot API. Токен никогда не логируется."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(payload or {}, doseq=True).encode("utf-8")
    request = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
        result = json.loads(raw)
        if not result.get("ok"):
            log(f"[telegram] {method}: {result.get('description', 'unknown error')}")
        return result
    except TimeoutError:
        # Штатный таймаут длинного getUpdates — не ошибка.
        if method != "getUpdates":
            log(f"[telegram] {method}: таймаут")
        return None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # pylint: disable=broad-exception-caught
            body = ""
        log(f"[telegram] {method}: HTTP {exc.code}: {body[:300]}")
    except urllib.error.URLError as exc:
        log(f"[telegram] {method}: сеть: {exc.reason}")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        safe = str(exc).replace(token, "***")[:300]
        log(f"[telegram] {method}: {type(exc).__name__}: {safe}")
    return None


def split_text(text, limit):
    """Разбить текст по строкам, не превышая лимит Telegram."""
    chunks = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if current and len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks or [""]


def send_message(token, chat_id, text, reply_markup=None, parse_mode=None):
    text = text or " "
    chunks = split_text(text, 4000)
    for index, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": "true",
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None and index == 0:
            payload["reply_markup"] = json.dumps(
                reply_markup, ensure_ascii=False)
        api_call(token, "sendMessage", payload)
    return True


def send_preformatted(token, chat_id, title, content):
    send_message(token, chat_id, title)
    for chunk in split_text(content, 3500):
        send_message(
            token, chat_id,
            f"<pre>{html.escape(chunk)}</pre>",
            parse_mode="HTML",
        )


def main_keyboard():
    return {
        "keyboard": [
            [{"text": "📊 Статус"}, {"text": "📈 Прогресс"}],
            [{"text": "🖥 Ресурсы"}, {"text": "📜 Логи"}],
            [{"text": "🧪 Логи анализа"}],
            [{"text": "🚀 Перезапустить"}, {"text": "⏹ Остановить"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def confirm_clean_keyboard():
    return {
        "inline_keyboard": [[
            {"text": "Да, сбросить всё", "callback_data": "clean:yes"},
            {"text": "Отмена", "callback_data": "clean:no"},
        ]]
    }


def confirm_action_keyboard(action):
    """Подтверждение опасного действия: restart или stop."""
    return {
        "inline_keyboard": [[
            {"text": "Да, подтверждаю", "callback_data": f"confirm:{action}:yes"},
            {"text": "Отмена", "callback_data": f"confirm:{action}:no"},
        ]]
    }


# ---------------------------------------------------------------------------
# Состояние сервиса и базы
# ---------------------------------------------------------------------------

def systemctl(*args, timeout=30):
    try:
        return subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log(f"[systemctl] {' '.join(args)}: {type(exc).__name__}: {exc}")
        return None


def service_state():
    result = systemctl(
        "show", SERVICE, "--no-pager",
        "-p", "ActiveState", "-p", "SubState",
        "-p", "MainPID", "-p", "ActiveEnterTimestamp",
    )
    state = {}
    if result and result.returncode == 0:
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                state[key] = value
    return state


def service_active(state=None):
    state = state or service_state()
    return state.get("ActiveState") in ("active", "activating", "reloading")


def service_elapsed_seconds(state=None):
    """Сколько работает unit.

    ActiveEnterTimestampMonotonic нельзя сравнивать с /proc/uptime:
    CLOCK_MONOTONIC не учитывает suspend, а uptime учитывает. Поэтому
    разбираем человекочитаемый ActiveEnterTimestamp в локальном времени.
    """
    state = state or service_state()
    stamp = (state.get("ActiveEnterTimestamp") or "").strip()
    parts = stamp.split()
    if len(parts) < 3:
        return 0
    try:
        started = datetime.strptime(
            f"{parts[1]} {parts[2]}", "%Y-%m-%d %H:%M:%S")
        return max(0, int((datetime.now() - started).total_seconds()))
    except ValueError:
        return 0


def format_duration(seconds):
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}д")
    if hours or days:
        parts.append(f"{hours}ч")
    parts.append(f"{minutes}м")
    return " ".join(parts)


def read_pid():
    try:
        with open(PID_FILE, "r", encoding="utf-8") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def done_count():
    if not os.path.isdir(DONE_DIR):
        return 0
    return len([
        name for name in os.listdir(DONE_DIR) if name.endswith(".done")
    ])


def worker_count():
    try:
        result = subprocess.run(
            ["ps", "-eo", "args"], capture_output=True, text=True, timeout=10)
        return sum(
            1 for line in result.stdout.splitlines()
            if "main.py --university" in line
        )
    except Exception:  # pylint: disable=broad-exception-caught
        return 0


def tail_file(path, max_bytes=20000):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def failure_lines():
    content = tail_file(BATCH_LOG)
    return [
        line.rstrip() for line in content.splitlines()
        if line.startswith("[fail]")
    ]


def clickhouse_client():
    try:
        import clickhouse_connect
        return clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            secure=os.getenv("CLICKHOUSE_SECURE", "False").lower()
            in ("true", "1", "yes"),
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log(f"[clickhouse] {type(exc).__name__}: {exc}")
        return None


def ch_query(sql):
    client = clickhouse_client()
    if client is None:
        return None
    try:
        return client.query(sql).result_rows
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log(f"[clickhouse] запрос не выполнен: {type(exc).__name__}: {exc}")
        return None
    finally:
        try:
            client.close()
        except Exception:  # pylint: disable=broad-exception-caught
            pass


def max_day():
    # agent_states пишется каждый день для всех агентов, поэтому это
    # канонический источник текущего дня. agent_relations — запасной
    # вариант, если состояния ещё не записались.
    # Возвращаем -1, если данных ещё нет: day_id начинается с нуля.
    rows = ch_query("SELECT max(day_id) FROM agent_states")
    if rows and rows[0][0] is not None:
        return int(rows[0][0])
    rows = ch_query("SELECT max(day_id) FROM agent_relations")
    if rows and rows[0][0] is not None:
        return int(rows[0][0])
    return -1


def db_summary():
    rows = ch_query(
        "SELECT sum(rows), formatReadableSize(sum(bytes_on_disk)) "
        "FROM system.parts WHERE active AND database = 'default'"
    )
    if not rows or rows[0][0] is None:
        return ""
    count = f"{int(rows[0][0]):,}".replace(",", " ")
    return f"{count} строк, {rows[0][1]}"


def progress_rows():
    return ch_query(
        "SELECT r.scenario_name, max(s.day_id) AS day "
        "FROM agent_states s "
        "JOIN simulation_runs r ON s.run_id = r.run_id "
        "GROUP BY r.scenario_name "
        "ORDER BY r.scenario_name"
    )


def timing_summary():
    """Средняя скорость завершённых прогонов и грубая оценка остатка."""
    exists = ch_query(
        "SELECT count() FROM system.tables "
        "WHERE database = 'default' AND name = 'run_timings'"
    )
    if not exists or not exists[0][0]:
        return None
    rows = ch_query(
        "SELECT count(), avg(wall_seconds), avg(simulation_seconds), "
        "avg(interactions) FROM run_timings "
        "WHERE implementation = 'python-v2' AND status = 'ok'"
    )
    if not rows or not rows[0][0]:
        return None
    count, wall, simulation, interactions = rows[0]
    count = int(count or 0)
    wall = float(wall or 0.0)
    simulation = float(simulation or 0.0)
    interactions = float(interactions or 0.0)
    if count <= 0 or wall <= 0:
        return None

    done = done_count()
    remaining = max(0, TOTAL_SCENARIOS - done)
    workers = max(1, worker_count())
    waves = (remaining + workers - 1) // workers
    eta_seconds = waves * wall
    return (
        f"Среднее время: <b>{wall / 60:.1f} мин</b> "
        f"(симуляция {simulation / 60:.1f} мин, "
        f"{interactions / 1e6:.1f} млн контактов)"
        f"\nОсталось волн: {waves}, оценка: <b>{format_duration(eta_seconds)}</b>"
    )


# ---------------------------------------------------------------------------
# Ресурсы сервера
# ---------------------------------------------------------------------------

def read_cpu_times():
    stats = {}
    with open("/proc/stat", "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("cpu"):
                continue
            parts = line.split()
            name = parts[0]
            values = [int(value) for value in parts[1:]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            stats[name] = (sum(values), idle)
    return stats


def cpu_usage():
    if not os.path.exists("/proc/stat"):
        return None
    try:
        first = read_cpu_times()
        time.sleep(0.4)
        second = read_cpu_times()
    except Exception:  # pylint: disable=broad-exception-caught
        return None

    usage = {}
    for name, (total, idle) in first.items():
        if name not in second:
            continue
        total_delta = second[name][0] - total
        idle_delta = second[name][1] - idle
        if total_delta <= 0:
            usage[name] = 0.0
        else:
            usage[name] = max(
                0.0, min(100.0, 100.0 * (total_delta - idle_delta) / total_delta))
    return usage


def memory_info():
    if not os.path.exists("/proc/meminfo"):
        return None
    info = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                info[key] = int(value.strip().split()[0])
    except Exception:  # pylint: disable=broad-exception-caught
        return None

    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(0, total - available)
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    swap_used = max(0, swap_total - swap_free)
    return used, total, swap_used, swap_total


def disk_line(path):
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    return f"  • <b>{html.escape(path)}</b>: {free_gb:.0f} ГБ свободно из {total_gb:.0f} ГБ"


def uptime_seconds():
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as handle:
            return float(handle.read().split()[0])
    except Exception:  # pylint: disable=broad-exception-caught
        return 0


def max_temperature():
    base = "/sys/class/thermal"
    if not os.path.isdir(base):
        return None
    values = []
    for name in os.listdir(base):
        if not name.startswith("thermal_zone"):
            continue
        path = os.path.join(base, name, "temp")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                value = float(handle.read().strip())
            if value > 1000:
                value /= 1000.0
            if -40 < value < 150:
                values.append(value)
        except (OSError, ValueError):
            continue
    return max(values) if values else None


def top_processes(limit=5):
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,pcpu,pmem,comm", "--sort=-pcpu"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        return []
    return result.stdout.splitlines()[:limit + 1]


# ---------------------------------------------------------------------------
# Тексты сообщений
# ---------------------------------------------------------------------------

def status_text():
    state = service_state()
    active = service_active(state)
    done = done_count()
    failures = failure_lines()
    day = max(0, max_day() + 1)
    workers = worker_count()
    elapsed = service_elapsed_seconds(state) if active else 0

    lines = ["<b>📊 Статус v2-corrected</b>"]
    if active:
        lines.append(
            f"Сервис: 🟢 {html.escape(state.get('ActiveState', '?'))}"
            f"/{html.escape(state.get('SubState', '?'))}")
        lines.append(
            f"PID: <code>{html.escape(state.get('MainPID', '0'))}</code>, "
            f"воркеров: {workers}")
        if elapsed:
            lines.append(f"В работе: {format_duration(elapsed)}")
    else:
        lines.append(
            f"Сервис: 🔴 {html.escape(state.get('ActiveState', 'не запущен'))}")

    lines.append(f"Готово сценариев: <b>{done}/{TOTAL_SCENARIOS}</b>")
    lines.append(f"Текущий день: <b>{day}/{TOTAL_DAYS}</b>")

    timing = timing_summary()
    if timing:
        lines.append(timing)

    summary = db_summary()
    if summary:
        lines.append(f"База: {summary}")

    disk = disk_line(EXTERNAL_DISK)
    if disk:
        lines.append(disk)

    analyzers = analyzer_processes()
    if analyzers:
        lines.append(f"Анализаторы: 🟢 {len(analyzers)} процесс(ов)")
    else:
        lines.append("Анализаторы: ⚪ не запущены")
    latest_log = latest_analyzer_log()
    if latest_log:
        stamp = datetime.fromtimestamp(
            os.path.getmtime(latest_log)).strftime("%d.%m %H:%M")
        lines.append(
            f"Лог анализа: <code>{html.escape(os.path.basename(latest_log))}</code>"
            f" ({stamp})")

    lines.append(f"Ошибок в логе: {len(failures)}")
    analyzer_failures = analyzer_failure_lines()
    if analyzer_failures:
        lines.append(
            f"⚠️ Traceback в логе анализа: {len(analyzer_failures)}")
    if failures:
        lines.append("Последние ошибки:")
        for failure in failures[-5:]:
            lines.append(f"<code>{html.escape(failure[:200])}</code>")
    return "\n".join(lines)


def progress_text():
    rows = progress_rows()
    if rows is None:
        return "⚠️ Не удалось прочитать прогресс из ClickHouse."
    if not rows:
        return "📈 Пока нет данных в базе."

    done = done_count()
    lines = [
        f"📈 Прогресс: готово {done}/{TOTAL_SCENARIOS}",
        f"Текущий день: {max(0, max_day() + 1)}/{TOTAL_DAYS}",
        "",
    ]
    for name, day in rows:
        day = int(day or 0)
        sim_date = SIM_START_DATE + timedelta(days=day)
        lines.append(
            f"{name}: день {day + 1}/{TOTAL_DAYS} "
            f"({sim_date.strftime('%d.%m.%Y')})")
    return "\n".join(lines)


def resources_text():
    lines = ["<b>🖥 Ресурсы сервера</b>"]

    usage = cpu_usage()
    if usage:
        total = usage.get("cpu")
        cores = [
            f"{index}:{value:.0f}%"
            for name, value in usage.items()
            if name != "cpu"
            for index in [int(name[3:])]
        ]
        lines.append(f"CPU: <b>{total:.0f}%</b>")
        if cores:
            lines.append(f"Ядра: <code>{' '.join(cores)}</code>")
    else:
        lines.append("CPU: данные недоступны")

    try:
        load = os.getloadavg()
        lines.append(f"Load average: {load[0]:.2f} {load[1]:.2f} {load[2]:.2f}")
    except OSError:
        pass

    memory = memory_info()
    if memory:
        used, total, swap_used, swap_total = memory
        lines.append(
            f"RAM: <b>{100 * used / total:.0f}%</b> "
            f"({used // 1024} МБ / {total // 1024} МБ)")
        if swap_total:
            lines.append(
                f"Swap: <b>{100 * swap_used / swap_total:.0f}%</b> "
                f"({swap_used // 1024} МБ / {swap_total // 1024} МБ)")
        else:
            lines.append("Swap: не подключён")

    uptime = uptime_seconds()
    if uptime:
        lines.append(f"Uptime: {format_duration(uptime)}")

    for path in ("/", EXTERNAL_DISK):
        line = disk_line(path)
        if line:
            lines.append(line)

    temperature = max_temperature()
    if temperature is not None:
        lines.append(f"Температура (max thermal zone): {temperature:.0f} °C")

    lines.append(f"Воркеров main.py: {worker_count()}")
    processes = top_processes()
    if processes:
        lines.append("Топ процессов:")
        for line in processes:
            lines.append(f"<code>{html.escape(line[:160])}</code>")
    return "\n".join(lines)


def logs_text():
    content = tail_file(BATCH_LOG)
    if not content:
        return "Файл batch.log не найден или пуст."
    return content[-3500:]


def watcher_logs_text():
    content = tail_file(os.path.join(OUTPUT_ROOT, "tg-watcher.log"))
    if not content:
        return "Файл tg-watcher.log не найден или пуст."
    return content[-3500:]


def latest_analyzer_log():
    """Самый свежий лог анализатора в data/v2-corrected."""
    candidates = []
    for pattern in ANALYZER_LOG_GLOBS:
        for path in glob.glob(os.path.join(OUTPUT_ROOT, pattern)):
            if os.path.isfile(path):
                try:
                    candidates.append((os.path.getmtime(path), path))
                except OSError:
                    pass
    if not candidates:
        return None
    return max(candidates)[1]


def analyzer_logs_text():
    path = latest_analyzer_log()
    if not path:
        return "Логи анализаторов не найдены в data/v2-corrected."
    content = tail_file(path, max_bytes=40000)
    if not content:
        return f"Файл {os.path.basename(path)} пуст."
    return f"Файл: {os.path.basename(path)}\n{content[-3500:]}"


def analyzer_processes():
    """Запущенные процессы анализаторов (без воркеров симуляции)."""
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,etime,cmd"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log(f"[analyzers] ps: {type(exc).__name__}: {exc}")
        return []
    found = []
    for line in result.stdout.splitlines():
        if any(name in line for name in ANALYZER_SCRIPTS):
            if "tg_batch_watcher.py" in line or "ps -eo" in line:
                continue
            found.append(line.strip())
    return found


def analyzer_failure_lines():
    """Traceback/падения в самом свежем логе анализатора."""
    path = latest_analyzer_log()
    if not path:
        return []
    content = tail_file(path, max_bytes=200000)
    markers = ("Traceback (most recent call last)", "MemoryError", "Killed")
    return [
        line.rstrip() for line in content.splitlines()
        if any(marker in line for marker in markers)
    ]


# ---------------------------------------------------------------------------
# Действия
# ---------------------------------------------------------------------------

def restart_batch():
    result = systemctl("restart", SERVICE, timeout=60)
    time.sleep(3)
    state = service_state()
    status = state.get("ActiveState", "unknown")
    text = f"🚀 Перезапуск: <b>{html.escape(status)}</b>"
    if result is not None and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if detail:
            text += f"\n<code>{html.escape(detail[:500])}</code>"
    return text


def stop_batch():
    result = systemctl("stop", SERVICE, timeout=60)
    time.sleep(2)
    state = service_state()
    status = state.get("ActiveState", "unknown")
    text = f"⏹ Остановка: <b>{html.escape(status)}</b>"
    if result is not None and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if detail:
            text += f"\n<code>{html.escape(detail[:500])}</code>"
    return text


def clean_restart():
    lines = ["🧹 <b>Чистый перезапуск</b>"]

    result = systemctl("stop", SERVICE, timeout=60)
    lines.append(
        "Сервис остановлен." if result and result.returncode == 0
        else "Не удалось остановить сервис.")

    client = clickhouse_client()
    if client is None:
        lines.append("ClickHouse недоступен, таблицы не очищены.")
    else:
        try:
            existing = {
                row[0] for row in client.query(
                    "SELECT name FROM system.tables WHERE database = 'default'"
                ).result_rows
            }
            for table in (
                "agent_states", "interactions", "agent_relations",
                "agent_registry", "simulation_runs", "run_timings",
            ):
                if table in existing:
                    client.command(f"TRUNCATE TABLE default.{table}")
            lines.append("Таблицы ClickHouse очищены.")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            lines.append(f"Ошибка очистки ClickHouse: {html.escape(str(exc))}")
        finally:
            try:
                client.close()
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    removed = 0
    for directory in (DONE_DIR, LOGS_DIR,
                      os.path.join(OUTPUT_ROOT, "timings")):
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if not (
                name.endswith(".done") or name.endswith(".log")
                or name.endswith(".json")
            ):
                continue
            try:
                os.remove(os.path.join(directory, name))
                removed += 1
            except OSError:
                pass
    for path in (BATCH_LOG, PID_FILE,
                 os.path.join(OUTPUT_ROOT, "batch_timings.jsonl")):
        try:
            if os.path.exists(path):
                os.remove(path)
                removed += 1
        except OSError:
            pass
    lines.append(f"Удалено файлов: {removed}.")

    result = systemctl("start", SERVICE, timeout=60)
    time.sleep(3)
    state = service_state()
    lines.append(
        f"Сервис: <b>{html.escape(state.get('ActiveState', 'unknown'))}</b>.")
    if result is not None and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if detail:
            lines.append(f"<code>{html.escape(detail[:500])}</code>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Обработка команд
# ---------------------------------------------------------------------------

def send_status(token, chat_id):
    send_message(
        token, chat_id, status_text(),
        reply_markup=main_keyboard(), parse_mode="HTML")


def send_progress(token, chat_id):
    send_message(
        token, chat_id, progress_text(), reply_markup=main_keyboard())


def send_resources(token, chat_id):
    send_message(
        token, chat_id, resources_text(),
        reply_markup=main_keyboard(), parse_mode="HTML")


def send_logs(token, chat_id):
    send_preformatted(token, chat_id, "📜 Последние строки batch.log:", logs_text())


def send_watcher_logs(token, chat_id):
    send_preformatted(
        token, chat_id, "📜 Последние строки tg-watcher.log:",
        watcher_logs_text())


def send_analyzer_logs(token, chat_id):
    send_preformatted(
        token, chat_id, "🧪 Последние строки лога анализатора:",
        analyzer_logs_text())


def ask_restart(token, chat_id):
    send_message(
        token, chat_id,
        "⚠️ <b>Перезапуск прогона</b>\n"
        "Сервис симуляции будет остановлен и запущен заново. "
        "Незавершённый сценарий начнётся с последней контрольной точки, "
        "поэтому его текущие данные могут быть потеряны.\n"
        "Подтвердить перезапуск?",
        reply_markup=confirm_action_keyboard("restart"), parse_mode="HTML")


def ask_stop(token, chat_id):
    send_message(
        token, chat_id,
        "⚠️ <b>Остановка прогона</b>\n"
        "Сервис симуляции будет остановлен. Уже записанные данные "
        "сохранятся, но новые сценарии перестанут запускаться.\n"
        "Подтвердить остановку?",
        reply_markup=confirm_action_keyboard("stop"), parse_mode="HTML")


def ask_clean_restart(token, chat_id):
    send_message(
        token, chat_id,
        "⚠️ <b>Чистый перезапуск</b>\n"
        "Будут остановлены воркеры, очищены таблицы ClickHouse, удалены "
        "маркеры done/, логи и batch.log. Затем матрица начнётся заново.\n"
        "Это действие необратимо.",
        reply_markup=confirm_clean_keyboard(), parse_mode="HTML")


def handle_message(token, allowed_chat_id, message):
    chat_id = str(message.get("chat", {}).get("id", ""))
    if chat_id != str(allowed_chat_id):
        send_message(token, chat_id, "Доступ запрещён.")
        return

    text = (message.get("text") or "").strip()
    if text.startswith("/"):
        command = text.split()[0].split("@")[0].lower()
        if command in ("/start", "/help"):
            send_message(
                token, chat_id, WELCOME,
                reply_markup=main_keyboard(), parse_mode="HTML")
        elif command == "/status":
            send_status(token, chat_id)
        elif command == "/progress":
            send_progress(token, chat_id)
        elif command == "/resources":
            send_resources(token, chat_id)
        elif command == "/logs":
            send_logs(token, chat_id)
        elif command in ("/analysis_logs", "/analyzers"):
            send_analyzer_logs(token, chat_id)
        elif command == "/watcher_log":
            send_watcher_logs(token, chat_id)
        elif command == "/restart":
            ask_restart(token, chat_id)
        elif command == "/stop":
            ask_stop(token, chat_id)
        elif command == "/clean_restart":
            ask_clean_restart(token, chat_id)
        else:
            send_message(
                token, chat_id, "Неизвестная команда.\n" + WELCOME,
                reply_markup=main_keyboard(), parse_mode="HTML")
        return

    if text == "📊 Статус":
        send_status(token, chat_id)
    elif text == "📈 Прогресс":
        send_progress(token, chat_id)
    elif text == "🖥 Ресурсы":
        send_resources(token, chat_id)
    elif text == "📜 Логи":
        send_logs(token, chat_id)
    elif text == "🧪 Логи анализа":
        send_analyzer_logs(token, chat_id)
    elif text == "🚀 Перезапустить":
        ask_restart(token, chat_id)
    elif text == "⏹ Остановить":
        ask_stop(token, chat_id)
    elif text:
        send_message(
            token, chat_id, "Выбери кнопку ниже.",
            reply_markup=main_keyboard())


def handle_callback(token, allowed_chat_id, callback):
    chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    callback_id = callback.get("id")
    if chat_id != str(allowed_chat_id):
        api_call(token, "answerCallbackQuery", {
            "callback_query_id": callback_id,
            "text": "Доступ запрещён.",
        })
        return

    data = callback.get("data", "")
    if data.startswith("confirm:"):
        parts = data.split(":", 2)
        if len(parts) != 3:
            api_call(token, "answerCallbackQuery", {
                "callback_query_id": callback_id,
            })
            return
        _, action, answer = parts
        if answer == "no":
            api_call(token, "answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "Отменено",
            })
            send_message(
                token, chat_id, "Действие отменено.",
                reply_markup=main_keyboard())
            return
        if action == "restart":
            api_call(token, "answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "Перезапускаю...",
            })
            send_message(token, chat_id, "⏳ Перезапускаю сервис...")
            send_message(
                token, chat_id, restart_batch(),
                reply_markup=main_keyboard(), parse_mode="HTML")
        elif action == "stop":
            api_call(token, "answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "Останавливаю...",
            })
            send_message(token, chat_id, "⏳ Останавливаю сервис...")
            send_message(
                token, chat_id, stop_batch(),
                reply_markup=main_keyboard(), parse_mode="HTML")
        else:
            api_call(token, "answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "Неизвестное действие",
            })
        return

    if data == "clean:yes":
        api_call(token, "answerCallbackQuery", {
            "callback_query_id": callback_id,
            "text": "Сбрасываю...",
        })
        send_message(token, chat_id, "⏳ Останавливаю прогон и чищу данные...")
        send_message(
            token, chat_id, clean_restart(),
            reply_markup=main_keyboard(), parse_mode="HTML")
    elif data == "clean:no":
        api_call(token, "answerCallbackQuery", {
            "callback_query_id": callback_id,
            "text": "Отменено",
        })
        send_message(
            token, chat_id, "Сброс отменён.",
            reply_markup=main_keyboard())
    else:
        api_call(token, "answerCallbackQuery", {
            "callback_query_id": callback_id,
        })


def handle_update(token, allowed_chat_id, update):
    if "message" in update:
        handle_message(token, allowed_chat_id, update["message"])
    elif "callback_query" in update:
        handle_callback(token, allowed_chat_id, update["callback_query"])


# ---------------------------------------------------------------------------
# Фоновые циклы
# ---------------------------------------------------------------------------

def prime_offset(token):
    response = api_call(token, "getUpdates", {
        "offset": -1,
        "timeout": 0,
        "limit": 1,
    }, timeout=15)
    if response and response.get("result"):
        return int(response["result"][-1]["update_id"]) + 1
    return 0


def poll_loop(token, chat_id, stop_event):
    offset = prime_offset(token)
    log("[bot] polling started")
    while not stop_event.is_set():
        response = api_call(token, "getUpdates", {
            "offset": offset,
            "timeout": POLL_TIMEOUT,
            "allowed_updates": json.dumps(["message", "callback_query"]),
        }, timeout=POLL_TIMEOUT + 10)
        if response is None:
            stop_event.wait(5)
            continue
        for update in response.get("result", []):
            offset = max(offset, int(update.get("update_id", 0)) + 1)
            try:
                handle_update(token, chat_id, update)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                log(f"[bot] ошибка обработки update: {type(exc).__name__}: {exc}")
    log("[bot] polling stopped")


def watcher_loop(token, chat_id, stop_event):
    last_alive = None
    last_done = done_count()
    last_fail_count = len(failure_lines())
    last_analyzer_fail_count = len(analyzer_failure_lines())
    last_update = datetime.min

    while not stop_event.is_set():
        state = service_state()
        alive = service_active(state)
        done = done_count()
        failures = failure_lines()
        now = datetime.now()

        if last_alive is None:
            last_alive = alive
        elif alive != last_alive:
            if alive:
                send_message(
                    token, chat_id,
                    "▶️ Прогон запущен.\n" + status_text(),
                    reply_markup=main_keyboard(), parse_mode="HTML")
            elif done >= TOTAL_SCENARIOS:
                send_message(
                    token, chat_id,
                    f"🏁 Матрица завершена: {done}/{TOTAL_SCENARIOS}.\n"
                    + status_text(),
                    reply_markup=main_keyboard(), parse_mode="HTML")
            else:
                send_message(
                    token, chat_id,
                    "⏹ Прогон остановлен.\n" + status_text(),
                    reply_markup=main_keyboard(), parse_mode="HTML")
            last_alive = alive
            last_update = now

        if len(failures) > last_fail_count:
            new_failures = failures[last_fail_count:]
            send_message(
                token, chat_id,
                "⚠️ Новые ошибки:\n" + "\n".join(new_failures[-5:]))
            last_fail_count = len(failures)

        analyzer_failures = analyzer_failure_lines()
        if len(analyzer_failures) > last_analyzer_fail_count:
            new_analyzer = analyzer_failures[last_analyzer_fail_count:]
            send_message(
                token, chat_id,
                "⚠️ Новые ошибки анализатора:\n"
                + "\n".join(new_analyzer[-5:]))
        last_analyzer_fail_count = len(analyzer_failures)

        if alive and (now - last_update >= UPDATE_EVERY or done != last_done):
            send_message(
                token, chat_id, status_text(),
                reply_markup=main_keyboard(), parse_mode="HTML")
            last_update = now
            last_done = done

        stop_event.wait(30)


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def main():
    load_env_file(os.path.join(ROOT, ".env"))
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log(
            "TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы. "
            "Добавьте их в .env и запустите скрипт снова.")
        return 2

    stop_event = threading.Event()

    def handle_signal(signum, _frame):
        log(f"[bot] signal {signum}, stopping")
        stop_event.set()
        RUNNING.clear()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    send_message(
        token, chat_id,
        "🤖 Бот запущен.\n" + status_text(),
        reply_markup=main_keyboard(), parse_mode="HTML")

    watcher = threading.Thread(
        target=watcher_loop, args=(token, chat_id, stop_event), daemon=True)
    watcher.start()

    poll_loop(token, chat_id, stop_event)
    watcher.join(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
