"""Telegram-наблюдатель за матричным прогоном v2-corrected.

Скрипт не обязателен для симуляции: он только читает batch.log, batch.pid
и каталог done/, а затем отправляет короткие статусы в Telegram.

Запуск:
    TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... \
        ./venv/bin/python scripts/tg_batch_watcher.py

Если токена нет, скрипт завершится с понятным сообщением и не затронет
работающий прогон.
"""

import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_ROOT = os.path.join(ROOT, "data", "v2-corrected")
BATCH_LOG = os.path.join(OUTPUT_ROOT, "batch.log")
PID_FILE = os.path.join(OUTPUT_ROOT, "batch.pid")
DONE_DIR = os.path.join(OUTPUT_ROOT, "done")
TOTAL_SCENARIOS = 42
UPDATE_EVERY = timedelta(minutes=30)


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


def telegram_send(token, chat_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with urllib.request.urlopen(url, data=data, timeout=15) as response:
            return response.status == 200
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[telegram] не удалось отправить сообщение: {exc}", flush=True)
        return False


def read_pid():
    try:
        with open(PID_FILE, "r", encoding="utf-8") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def process_alive(pid):
    if pid is not None:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            pass

    # При запуске через systemd PID-файл может отсутствовать или быть
    # старым. Тогда истина — состояние unit'а, а не файл.
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "automata-batch.service"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() == "active"
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def done_count():
    if not os.path.isdir(DONE_DIR):
        return 0
    return len([name for name in os.listdir(DONE_DIR) if name.endswith(".done")])


def failure_lines():
    if not os.path.exists(BATCH_LOG):
        return []
    with open(BATCH_LOG, "r", encoding="utf-8", errors="replace") as handle:
        return [line.rstrip() for line in handle if line.startswith("[fail]")]


def status_text(started_at, last_done):
    done = done_count()
    failures = failure_lines()
    pid = read_pid()
    alive = process_alive(pid)
    elapsed = datetime.now() - started_at
    text = (
        f"v2-corrected: {done}/{TOTAL_SCENARIOS} готово\n"
        f"прошло: {str(elapsed).split('.')[0]}\n"
        f"воркер: {'работает' if alive else 'остановлен'} (pid={pid})\n"
        f"ошибок: {len(failures)}"
    )
    if failures:
        text += "\n\nПоследние ошибки:\n" + "\n".join(failures[-5:])
    if done != last_done and done > last_done:
        text += f"\n\nНовых завершений: {done - last_done}"
    return text


def main():
    load_env_file(os.path.join(ROOT, ".env"))
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print(
            "TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы. "
            "Добавьте их в .env и запустите скрипт снова.",
            flush=True,
        )
        return 2

    started_at = datetime.now()
    last_update = datetime.now()
    last_done = done_count()
    telegram_send(
        token, chat_id,
        f"Наблюдение за v2-corrected запущено.\n"
        f"Готово сценариев: {last_done}/{TOTAL_SCENARIOS}",
    )
    print("[telegram] стартовое сообщение отправлено", flush=True)

    while True:
        done = done_count()
        alive = process_alive(read_pid())
        now = datetime.now()
        if not alive:
            text = status_text(started_at, last_done)
            text += "\n\nПрогон завершён." if done >= TOTAL_SCENARIOS else "\n\nПроцесс остановлен."
            telegram_send(token, chat_id, text)
            print("[telegram] финальное сообщение отправлено", flush=True)
            return 0 if done >= TOTAL_SCENARIOS and not failure_lines() else 1
        if now - last_update >= UPDATE_EVERY or done != last_done:
            telegram_send(token, chat_id, status_text(started_at, last_done))
            print(f"[telegram] статус: {done}/{TOTAL_SCENARIOS}", flush=True)
            last_update = now
            last_done = done
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
