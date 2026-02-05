import pandas as pd
import networkx as nx
from datetime import timedelta
import os
import glob

def analyze_contact_groups(df, current_date_str, days=100, min_group_size=3):
    df['Дата'] = pd.to_datetime(df['Дата'])
    current_date = pd.to_datetime(current_date_str)
    start_date = current_date - timedelta(days=days)
    
    df_recent = df[(df['Дата'] >= start_date) & (df['Дата'] <= current_date)].copy()
    df_recent = df_recent[df_recent['Успех'].isin(['success', 'fail'])]
    
    agents = pd.unique(df_recent[['Источник', 'Цель']].values.ravel('K'))
    
    G = nx.Graph()
    G.add_nodes_from(agents)
    
    edges = df_recent.groupby(['Источник', 'Цель']).size().reset_index().loc[:, ['Источник', 'Цель']]
    edges_rev = edges.rename(columns={'Источник':'Цель', 'Цель':'Источник'})
    all_edges = pd.concat([edges, edges_rev], ignore_index=True)
    edge_tuples = list(all_edges.itertuples(index=False, name=None))
    G.add_edges_from(edge_tuples)
    
    cliques = list(nx.find_cliques(G))
    large_cliques = [clq for clq in cliques if len(clq) >= min_group_size]
    
    return len(large_cliques), large_cliques


folder_path = "batch_results"
pattern = os.path.join(folder_path, "interaction_log_*.csv")
files = sorted(glob.glob(pattern))

group_counts_by_num = {}

for file in files:
    num = int(os.path.basename(file).split('_')[-1].split('.')[0])
    print(f"Обрабатываю файл {file} ...")
    df = pd.read_csv(file)
    current_date_str = df['Дата'].max()
    count, groups = analyze_contact_groups(df, current_date_str, days=100, min_group_size=3)
    group_counts_by_num[num] = count

summary_path = "batch_analysis/summary_stats.csv"
summary_df = pd.read_csv(summary_path)

if 'simulation_num' in summary_df.columns:
    summary_df['group_count_3plus'] = summary_df['simulation_num'].map(group_counts_by_num).fillna(0).astype(int)
else:
    summary_df['group_count_3plus'] = summary_df.index.to_series().add(1).map(group_counts_by_num).fillna(0).astype(int)

summary_df.to_csv(summary_path, index=False)
print(f"Обновленный summary_stats.csv сохранён с новым столбцом group_count_3plus")