import os
import pandas as pd

log_folder = "batch_results"
output_folder = "batch_analysis"
os.makedirs(output_folder, exist_ok=True)

interaction_files = [f for f in os.listdir(log_folder) if f.startswith("interaction_log") and f.endswith(".csv")]

for file in interaction_files:
    run_id = file.split('_')[-1].split('.')[0]  # извлекаем номер симуляции
    df = pd.read_csv(os.path.join(log_folder, file))

    # Фильтрация только успешных взаимодействий
    df = df[df['Успех'] == 'success']

    # Приведение пар агентов к нормализованному виду
    df['agent_pair'] = df.apply(lambda row: tuple(sorted([row['Источник'], row['Цель']])), axis=1)

    # Подсчёт количества взаимодействий между каждой парой
    pairs_df = df.groupby('agent_pair').size().reset_index(name='interactions')

    # Классификация по частоте
    pairs_df['frequency_class'] = pd.cut(
        pairs_df['interactions'],
        bins=[0, 5, 15, 1000],
        labels=['Rarely', 'Sometimes', 'Frequently']
    )

    # Подсчёт количества пар в каждом классе и сохранение в отдельный CSV
    frequency_counts = pairs_df['frequency_class'].value_counts().sort_index()
    frequency_counts_df = frequency_counts.reset_index()
    frequency_counts_df.columns = ['frequency_class', 'pair_count']
    freq_output_path = os.path.join(output_folder, f"frequency_summary_{run_id}.csv")
    frequency_counts_df.to_csv(freq_output_path, index=False)

    # Сортировка и сохранение
    pairs_df = pairs_df.sort_values(by="interactions", ascending=False)
    output_path = os.path.join(output_folder, f"analysis_interaction_{run_id}.csv")
    pairs_df.to_csv(output_path, index=False)

print(f"Анализ по каждому взаимодействию сохранён в папке {output_folder}")
