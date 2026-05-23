import os
import pandas as pd
import numpy as np
import clickhouse_connect
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')
plt.rcParams['font.family'] = 'DejaVu Sans'

ROOT = Path(__file__).resolve().parent
PLOTS_DIR = ROOT / 'data' / 'plots'
OUTPUT_DIR = ROOT / 'data' / 'output'
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Connecting to ClickHouse...")
db = clickhouse_connect.get_client(
    host=os.getenv("CLICKHOUSE_HOST", "db.georgytadjiev.ink"),
    port=int(os.getenv("CLICKHOUSE_PORT", "443")),
    username=os.getenv("CLICKHOUSE_USER", "default"),
    password=os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass"),
    secure=os.getenv("CLICKHOUSE_SECURE", "True").lower() in ("true", "1", "yes"),
    connect_timeout=120, send_receive_timeout=120
)

# Use a highly heterogeneous run
run_id = 'a764184e-96d5-4540-a21b-9ea5c68936e0'
print(f"Using run_id: {run_id}")

# ==========================================
# 1. Топологический детерминизм (Entropy)
# ==========================================
print("Calculating Entropy (Topological Determinism)...")
entropy_query = f"""
SELECT 
    semester,
    avg(entropy) as mean_entropy
FROM (
    SELECT 
        from_id,
        multiIf(day_id <= 153, 1, day_id <= 303, 2, day_id <= 456, 3, day_id <= 606, 4,
                day_id <= 759, 5, day_id <= 909, 6, day_id <= 1062, 7, 8) AS semester,
        -sum((cnt / total) * log(cnt / total)) as entropy
    FROM (
        SELECT 
            from_id,
            to_id,
            day_id,
            count() as cnt
        FROM interactions
        WHERE run_id = '{run_id}'
        GROUP BY from_id, to_id, day_id
    ) AS pairs
    JOIN (
        SELECT 
            from_id,
            day_id,
            count() as total
        FROM interactions
        WHERE run_id = '{run_id}'
        GROUP BY from_id, day_id
    ) AS totals ON pairs.from_id = totals.from_id AND pairs.day_id = totals.day_id
    GROUP BY from_id, semester
)
GROUP BY semester
ORDER BY semester
"""
try:
    df_entropy = db.query_df(entropy_query)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(df_entropy['semester'], df_entropy['mean_entropy'], marker='o', lw=3, color='#8E24AA')
    ax.set_title("Падение энтропии выбора партнера (Свобода выбора)", fontsize=14)
    ax.set_xlabel("Семестр")
    ax.set_ylabel("Средняя энтропия Шеннона (бит)")
    ax.set_ylim(bottom=0)
    ax.grid(True, ls='--', alpha=0.6)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / '20_entropy_collapse.pdf')
    fig.savefig(PLOTS_DIR / '20_entropy_collapse.png', dpi=150)
    print("Entropy plot saved.")
except Exception as e:
    print(f"Error in entropy: {e}")

# ==========================================
# 2. Эффект бабочки Деструктора
# ==========================================
print("Calculating Destructor Cascades...")
cascade_query = f"""
SELECT
    prev_type,
    prev_to_archetype,
    sum(type = -1) AS current_failures,
    count() AS total_current
FROM (
    SELECT 
        from_id,
        type,
        lagInFrame(type, 1) OVER (PARTITION BY from_id ORDER BY day_id, slot_id, to_id) AS prev_type,
        lagInFrame(ar.archetype, 1) OVER (PARTITION BY from_id ORDER BY day_id, slot_id, to_id) AS prev_to_archetype
    FROM interactions i
    JOIN agent_registry ar ON i.run_id = ar.run_id AND i.to_id = ar.agent_id
    WHERE i.run_id = '{run_id}'
)
WHERE prev_type IS NOT NULL
GROUP BY prev_type, prev_to_archetype
"""
try:
    df_casc = db.query_df(cascade_query)
    df_casc['failure_rate'] = df_casc['current_failures'] / df_casc['total_current'] * 100
    
    # Filter only refusals and ensure enough data points
    refusals = df_casc[(df_casc['prev_type'] == 0) & (df_casc['total_current'] > 100)].sort_values('failure_rate', ascending=False)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=refusals, x='failure_rate', y='prev_to_archetype', ax=ax, palette='Reds_r')
    
    baseline = df_casc[df_casc['prev_type'] == 1]['failure_rate'].mean()
    if pd.isna(baseline): baseline = 0
    ax.axvline(baseline, color='blue', ls='--', lw=2, label='Базовый шанс провала (после успеха)')
    
    ax.set_title("Влияние полученного отказа на следующий контакт инициатора", fontsize=14)
    ax.set_xlabel("Вероятность провала (%) следующего контакта")
    ax.set_ylabel("Архетип, отказавший в предыдущем контакте")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / '21_destructor_cascade.pdf')
    fig.savefig(PLOTS_DIR / '21_destructor_cascade.png', dpi=150)
    print("Cascade plot saved.")
except Exception as e:
    print(f"Error in cascade: {e}")

# ==========================================
# 3. Эхо-камеры эмоций
# ==========================================
print("Calculating Emotion Polarization...")
echo_query = f"""
SELECT 
    day_id,
    splitByChar('-', string_id)[2] as faculty,
    avg(sadness_joy) as mean_joy
FROM agent_states s
JOIN agent_registry r ON s.run_id = r.run_id AND s.agent_id = r.agent_id
WHERE s.run_id = '{run_id}' AND day_id % 7 = 0
GROUP BY day_id, faculty
ORDER BY day_id
"""
try:
    df_echo = db.query_df(echo_query)
    fig, ax = plt.subplots(figsize=(10, 5))
    for fac in df_echo['faculty'].unique():
        sub = df_echo[df_echo['faculty'] == fac]
        # Smooth the line
        ax.plot(sub['day_id'], sub['mean_joy'].rolling(5, min_periods=1).mean(), label=f'Факультет {fac}', lw=2)
    
    ax.set_title("Эмоциональная поляризация факультетов (Эхо-камеры)", fontsize=14)
    ax.set_xlabel("Модельный день")
    ax.set_ylabel("Ось Печаль-Радость (сглаженная)")
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(True, ls='--', alpha=0.5)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / '22_emotion_echo.pdf')
    fig.savefig(PLOTS_DIR / '22_emotion_echo.png', dpi=150)
    print("Echo plot saved.")
except Exception as e:
    print(f"Error in echo chambers: {e}")

print("All done!")
