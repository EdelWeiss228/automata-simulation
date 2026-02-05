import pandas as pd

def add_average_row_to_summary(file_path):
    # Читаем CSV
    summary_df = pd.read_csv(file_path)

    # Все колонки кроме 'run_id' считаем числовыми (предполагаем)
    numeric_cols = summary_df.columns.drop('run_id')

    # Средние значения по числовым колонкам
    mean_values = summary_df[numeric_cols].mean().round(2)

    # Создаем серию для средней строки, ставим 'avg' в run_id
    mean_row = pd.Series(data=mean_values.values, index=numeric_cols)
    mean_row['run_id'] = 'avg'

    # Удаляем старую строку с avg, если есть
    summary_df = summary_df[summary_df['run_id'] != 'avg']

    # Добавляем новую строку со средними
    summary_df = pd.concat([summary_df, mean_row.to_frame().T], ignore_index=True)

    # Сохраняем обратно
    summary_df.to_csv(file_path, index=False)
    print(f"Updated average row saved to: {file_path}")

if __name__ == "__main__":
    path = "batch_analysis/summary_stats.csv"
    add_average_row_to_summary(path)