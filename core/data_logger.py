import csv
import os
import datetime

class DataLogger:
    def __init__(self, log_dir: str = "data/output"):
        self.log_dir = log_dir

    def log_agent_states(self, filepath: str, current_date: datetime.date, agents: dict, is_first_run: bool):
        """Записывает текущее состояние всех агентов в CSV."""
        mode = "w" if is_first_run else "a"
        file_exists = os.path.isfile(filepath)
        
        with open(filepath, mode, newline='', encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_first_run or not file_exists:
                writer.writerow(["Дата", "Имя агента", "Эмоции", "Предикаты"])
            
            for agent in agents.values():
                emotion_str = "; ".join(f"{k}:{v}" for k, v in agent.get_emotions().items())
                pred_strs = []
                for target, preds in agent.relations.items():
                    pred_str = f"{target}=" + ",".join(f"{k}:{v}" for k, v in preds.items())
                    pred_strs.append(pred_str)
                writer.writerow([current_date.isoformat(), agent.name, emotion_str, " | ".join(pred_strs)])

    def log_interactions(self, filepath: str, current_date: datetime.date, interactions: list, is_first_run: bool):
        """Записывает акты взаимодействия в CSV."""
        mode = "w" if is_first_run else "a"
        file_exists = os.path.isfile(filepath)
        
        with open(filepath, mode, newline='', encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_first_run or not file_exists:
                writer.writerow(["Дата", "Источник", "Цель", "Успех"])
            
            for a_from, a_to, success in interactions:
                writer.writerow([current_date.isoformat(), a_from, a_to, success])
