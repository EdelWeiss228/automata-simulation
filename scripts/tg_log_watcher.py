import os
import time
import signal
import threading
import subprocess
import telebot
from telebot import types
from dotenv import load_dotenv

# Загрузка конфигов
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
LOG_FILE = "simulation_batch.log"
PID_FILE = "simulation_batch.pid"

if not TOKEN or not CHAT_ID:
    print("Ошибка: TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены в .env")
    exit(1)

bot = telebot.TeleBot(TOKEN)

def get_status():
    if not os.path.exists(PID_FILE):
        return "🔴 Симуляция не запущена (PID файл отсутствует)."
    
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        
        # Проверка существования процесса
        os.kill(pid, 0)
        
        # Читаем последние строки лога
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()
                last_logs = "".join(lines[-10:])
            return f"🟢 Работает (PID: {pid})\n\nПоследние логи:\n```\n{last_logs}\n```"
        return f"🟢 Работает (PID: {pid}), но лог-файл пуст."
    except (ProcessLookupError, ValueError, OverflowError):
        return "🔴 Процесс не найден (упал или завершился)."
    except Exception as e:
        return f"⚠️ Ошибка при проверке статуса: {e}"

def restart_simulation():
    # 1. Убиваем старые процессы
    try:
        subprocess.run("ps aux | grep run_research_batch.py | grep -v grep | awk '{print $2}' | xargs kill -9", shell=True)
        subprocess.run("ps aux | grep main.py | grep -v grep | awk '{print $2}' | xargs kill -9", shell=True)
    except:
        pass
    
    # 2. Очищаем базу (опционально, но обычно нужно для рестарта)
    try:
        from clickhouse_connect import get_client
        client = get_client(host='localhost', port=8123, username='default', password='clickhouse_pass')
        client.command("TRUNCATE TABLE agent_states")
        client.command("TRUNCATE TABLE agent_relations")
        client.command("TRUNCATE TABLE interactions")
        client.command("TRUNCATE TABLE agent_registry")
        client.command("TRUNCATE TABLE simulation_runs")
        client.close()
    except:
        pass

    # 3. Запускаем заново
    log_f = open(LOG_FILE, "w")
    process = subprocess.Popen(["./venv/bin/python", "scripts/run_research_batch.py"], 
                               stdout=log_f, stderr=log_f, start_new_session=True)
    
    with open(PID_FILE, "w") as f:
        f.write(str(process.pid))
    
    return f"🚀 Симуляция перезапущена! (PID: {process.pid})"

def get_resources():
    try:
        import psutil
        # Нужно задать интервал, иначе при первом вызове всегда будет 0.0
        cpu_total = psutil.cpu_percent(interval=0.5)
        cpu_cores = psutil.cpu_percent(interval=0.5, percpu=True)
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk_root = psutil.disk_usage('/')
        
        # Проверяем внешний диск, если он смонтирован
        ext_path = "/run/media/georgiy/home_external"
        ext_str = ""
        cores_str = ", ".join([f"{c}%" for c in cpu_cores])
        if os.path.exists(ext_path):
            disk_ext = psutil.disk_usage(ext_path)
            ext_str = f"  • <b>Диск (External)</b>: {disk_ext.free//(1024**3)} GB свободно\n"
        
        return (
            f"🖥 <b>Ресурсы сервера:</b>\n"
            f"  • <b>CPU</b>: {cpu_total}% (Всего)\n"
            f"  • <b>Ядра</b>: <code>{cores_str}</code>\n"
            f"  • <b>RAM</b>: {ram.percent}% ({ram.used//(1024**2)}MB / {ram.total//(1024**2)}MB)\n"
            f"  • <b>Swap</b>: {swap.percent}% ({swap.used//(1024**2)}MB / {swap.total//(1024**2)}MB)\n"
            f"  • <b>Диск (Root /)</b>: {disk_root.free//(1024**3)} GB свободно\n"
            f"{ext_str}"
        )
    except Exception as e:
        return f"⚠️ Ошибка получения ресурсов: {e}"

def get_detailed_progress():
    try:
        from clickhouse_connect import get_client
        client = get_client(host='localhost', port=8123, username='default', password='clickhouse_pass')
        query = """
            SELECT r.scenario_name, MAX(s.day_id) as day
            FROM agent_states s 
            JOIN simulation_runs r ON s.run_id = r.run_id 
            GROUP BY r.scenario_name
            ORDER BY day DESC
        """
        result = client.query(query)
        client.close()
        
        if not result.result_rows:
            return "📈 Пока нет данных в базе."
            
        lines = ["📈 **Текущий прогресс (по базе):**"]
        for row in result.result_rows:
            name, day = row
            # Примерный месяц
            months = ["Сентябрь", "Октябрь", "Ноябрь", "Декабрь", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь"]
            m_idx = min(day // 30, len(months)-1)
            lines.append(f"• `{name}`: **{day} день** ({months[m_idx]})")
            
        return "\n".join(lines)
    except Exception as e:
        return f"⚠️ Ошибка БД: {e}"

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_status = types.KeyboardButton("📊 Статус")
    btn_prog = types.KeyboardButton("📈 Прогресс")
    btn_res = types.KeyboardButton("🖥 Ресурсы")
    btn_logs = types.KeyboardButton("📜 Фулл логи")
    btn_restart = types.KeyboardButton("🚀 Рестарт")
    
    markup.row(btn_status, btn_prog)
    markup.row(btn_res, btn_logs)
    markup.row(btn_restart)
    bot.reply_to(message, "Бот мониторинга симуляции коллектива автоматов\nИспользуй кнопки ниже:", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if str(message.chat.id) != str(CHAT_ID):
        bot.reply_to(message, "Доступ запрещен.")
        return

    if message.text == "📊 Статус":
        bot.send_message(CHAT_ID, get_status(), parse_mode="HTML")
    elif message.text == "📈 Прогресс":
        bot.send_message(CHAT_ID, get_detailed_progress(), parse_mode="Markdown")
    elif message.text == "🖥 Ресурсы":
        bot.send_message(CHAT_ID, get_resources(), parse_mode="HTML")
    elif message.text == "📜 Фулл логи":
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                content = f.read()[-3000:] # Последние 3к символов
            bot.send_message(CHAT_ID, f"Последние логи:\n<pre>{content}</pre>", parse_mode="HTML")
        else:
            bot.send_message(CHAT_ID, "Файл лога не найден.")
    elif message.text == "🚀 Рестарт симуляции":
        msg = bot.send_message(CHAT_ID, "⏳ Перезапускаю всё (10 потоков + очистка ClickHouse)... Подожди.")
        res = restart_simulation()
        bot.edit_message_text(res, CHAT_ID, msg.message_id)

# --- Фоновая задача для слежения за логами (Live Feed) ---
def log_tailer():
    """Следит за файлом лога and пересылает важные строки (с поддержкой ротации файла)."""
    print("Log Tailer: Запущен.")
    
    last_inode = None
    f = None
    
    while True:
        try:
            if not os.path.exists(LOG_FILE):
                time.sleep(0.1)
                continue
                
            current_stat = os.stat(LOG_FILE)
            current_inode = current_stat.st_ino
            current_size = current_stat.st_size
            
            # Если файл изменился (пересоздан) или уменьшился (Truncate)
            if current_inode != last_inode or (f and current_size < f.tell()):
                if f: f.close()
                f = open(LOG_FILE, "r")
                # Если файл новый/обрезанный - читаем с начала, иначе с конца
                if last_inode is not None:
                    f.seek(0)
                else:
                    f.seek(0, os.SEEK_END)
                last_inode = current_inode
                print(f"Log Tailer: Файл {LOG_FILE} переоткрыт (Size: {current_size}).")
            
            line = f.readline()
            if not line:
                time.sleep(0.1) # Ускоряем опрос до 0.1 сек
                continue
                
            clean_line = line.strip()
            if not clean_line: continue
            
            # Фильтруем важные сообщения
            if "[Progress]" in clean_line or "[1/" in clean_line or "Ошибка" in clean_line or "Выполнение:" in clean_line or "[System]" in clean_line or "Начинаем серию" in clean_line or "Traceback" in clean_line or "AttributeError" in clean_line:
                bot.send_message(CHAT_ID, f"🔔 {clean_line}")
                
        except Exception as e:
            print(f"Ошибка в tailer: {e}")
            time.sleep(1)

if __name__ == "__main__":
    # Запуск тайлера в отдельном потоке
    threading.Thread(target=log_tailer, daemon=True).start()
    
    print("Bot: Запущен...")
    while True:
        try:
            bot.polling(none_stop=True, interval=3, timeout=20)
        except Exception as e:
            print(f"Ошибка полинга: {e}")
            time.sleep(5)
