import os
import pandas as pd

log_folder = "batch_results"
output_folder = "batch_analysis"
os.makedirs(output_folder, exist_ok=True)

interaction_files = [f for f in os.listdir(log_folder) if f.startswith("interaction_log") and f.endswith(".csv")]

summary_data = []

for file in interaction_files:
    run_id = file.split('_')[-1].split('.')[0]  # извлекаем номер симуляции
    df = pd.read_csv(os.path.join(log_folder, file))

    # Приведение пар агентов к нормализованному виду
    df['agent_pair'] = df.apply(lambda row: tuple(sorted([row['Источник'], row['Цель']])), axis=1)

    # Подсчёт количества взаимодействий между каждой парой
    pairs_df = df.groupby('agent_pair').size().reset_index(name='interactions')

    mean_interactions = pairs_df['interactions'].mean()
    max_interactions = pairs_df['interactions'].max()
    min_interactions = pairs_df['interactions'].min()

    # Подсчёт количества уникальных агентов в данном файле
    unique_agents = pd.unique(df[['Источник', 'Цель']].values.ravel())

    summary_data.append({
        'run_id': int(run_id),
        'mean_interactions': round(mean_interactions, 2),
        'max_interactions': round(max_interactions, 2),
        'min_interactions': round(min_interactions, 2),
    })

# Создаём DataFrame со сводной статистикой
summary_df = pd.DataFrame(summary_data)

# Сортируем по run_id для порядка
summary_df = summary_df.sort_values(by='run_id')

# Сохраняем в CSV
summary_path = os.path.join(output_folder, "summary_stats.csv")

summary_df.to_csv(summary_path, index=False)



# Перезаписываем CSV с добавленной строкой
summary_df.to_csv(summary_path, index=False)

print(f"Сводная статистика сохранена в {summary_path}")