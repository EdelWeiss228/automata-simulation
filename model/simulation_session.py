import os
import datetime
from model.collective import Collective
from core.data_logger import DataLogger

class SimulationSession:
    """
    Класс, инкапсулирующий логику сессии симуляции.
    Отвечает за управление коллективом, шаги времени и сохранение данных.
    """
    def __init__(self, collective=None, output_dir="data/output"):
        self.collective = collective if collective else Collective()
        self.logger = DataLogger()
        self.output_dir = output_dir
        
        self.first_log_states = True
        self.first_log_interactions = True
        self.simulation_started = False
        
        # Убеждаемся, что директория для вывода существует
        os.makedirs(self.output_dir, exist_ok=True)

    @property
    def current_step(self):
        return self.collective.current_step

    @property
    def current_date(self):
        return self.collective.current_date

    def run_day(self):
        """Выполняет один цикл симуляции дня и логирует результаты."""
        # Начальный лог состояний перед первым шагом
        if not self.simulation_started:
            self.log_states()
            self.simulation_started = True

        # Выполнение цикла
        interactions = self.collective.perform_full_day_cycle(interactive=False)

        # Логирование результатов дня
        self.log_interactions(interactions)
        self.log_states()

        return interactions

    def log_states(self):
        """Записывает текущие состояния агентов в файл."""
        states_file = os.path.join(self.output_dir, "agent_states.csv")
        self.logger.log_agent_states(
            states_file, 
            self.collective.current_date, 
            self.collective.agents, 
            self.first_log_states
        )
        self.first_log_states = False

    def log_interactions(self, interactions):
        """Записывает взаимодействия за день в файл."""
        interactions_file = os.path.join(self.output_dir, "interaction_log.csv")
        self.logger.log_interactions(
            interactions_file, 
            self.collective.current_date, 
            interactions, 
            self.first_log_interactions
        )
        self.first_log_interactions = False

    def reset(self, new_collective=None):
        """Сбрасывает сессию симуляции."""
        self.collective = new_collective if new_collective else Collective()
        self.first_log_states = True
        self.first_log_interactions = True
        self.simulation_started = False
        os.makedirs(self.output_dir, exist_ok=True)
