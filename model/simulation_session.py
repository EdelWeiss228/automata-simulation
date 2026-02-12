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
        self.gui_active = False # Флаг для динамического управления синхронизацией
        
        # Убеждаемся, что директория для вывода существует
        os.makedirs(self.output_dir, exist_ok=True)

    @property
    def current_step(self):
        return self.collective.current_step

    @property
    def current_date(self):
        return self.collective.current_date

    def ensure_relationships(self):
        """
        Гарантирует, что все агенты имеют записи об отношениях друг с другом.
        Вызывается перед началом симуляции для подготовки мира.
        """
        from core.agent_factory import AgentFactory
        agent_names = list(self.collective.agents.keys())
        total = len(agent_names)
        
        if total > 500:
            print(f"Инициализация связей для {total} агентов (~{total*total//10**6}M связей)...", flush=True)
            
        for i, agent in enumerate(self.collective.agents.values()):
            if total > 500 and i % (total // 10) == 0:
                print(f"  Подготовка связей: {int(i/total*100)}%...", flush=True)
            AgentFactory.initialize_agent_relations(agent, agent_names)
            
        if total > 500:
            print("Связи готовы.", flush=True)

    def load_scenario(self, scenario_path):
        """Загружает мир из сценария JSON."""
        import json
        from scripts.run_headless import generate_research_agents
        
        with open(scenario_path, 'r', encoding='utf-8') as f:
            scenario = json.load(f)
        
        agents = generate_research_agents(scenario)
        self.reset()
        for agent in agents:
            self.collective.add_agent(agent)
            
        self.total_steps = scenario.get("steps", 100)
        self.ensure_relationships()

    def create_template_scenario(self, path):
        """Создает шаблонный JSON-сценарий для исследований."""
        import json
        import random
        from model.archetypes import ArchetypeEnum
        
        template = {
            "total_agents": 100,
            "agent_counts": {arch.name: 0 for arch in ArchetypeEnum},
            "emotion_dist": "Normal",
            "emotion_params": {"mean": 0.0, "std": 1.0, "min": -3.0, "max": 3.0},
            "steps": 50,
            "seed": random.randint(0, 1000000)
        }
        
        # Распределяем 100 агентов поровну для примера
        archs = list(ArchetypeEnum)
        for i in range(100):
            arch = archs[i % len(archs)]
            template["agent_counts"][arch.name] += 1
            
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=4, ensure_ascii=False)
        print(f"Шаблон сценария успешно создан: {path}")

    def run_scenario(self, scenario_path, override_steps=None):
        """Полный цикл: загрузка -> инициализация -> запуск без GUI."""
        self.load_scenario(scenario_path)
        
        steps = override_steps if override_steps is not None else self.total_steps
        print(f"Запуск сценария {os.path.basename(scenario_path)} ({steps} шагов)...", flush=True)
        
        for step in range(steps):
            print(f"Шаг {step+1}/{steps}...", flush=True)
            self.run_day()
            
        print("--- РАСЧЕТ ЗАВЕРШЕН ---", flush=True)

    def run_day(self):
        """Выполняет один цикл симуляции дня и логирует результаты."""
        # Начальный лог состояний перед первым шагом
        if not self.simulation_started:
            # Снимаем начальный срез (всегда с отношениями по запросу пользователя)
            self.collective._sync_from_cpp(sync_relations=True)
            self.log_states()
            self.simulation_started = True

        # Выполнение цикла
        interactions = self.collective.perform_full_day_cycle(interactive=False)

        # Логирование результатов дня
        # Синхронизируем ПОЛНЫЕ данные из C++ обратно в Python ТОЛЬКО если нам это нужно (для GUI)
        # В headless режиме мы это пропускаем, так как C++ сам пишет логи
        is_headless = not hasattr(self, 'gui_active') or not self.gui_active 
        
        if self.collective.cpp_engine and is_headless:
            # В тихом режиме НЕ синхронизируем отношения в Python ради скорости
            self.collective._sync_from_cpp(sync_relations=False)
        else:
            # В GUI режиме синхронизируем всё для отрисовки
            self.collective._sync_from_cpp(sync_relations=True)
        
        self.log_interactions(interactions)
        self.log_states()

        return interactions

    def log_states(self):
        """Записывает текущие состояния агентов в файл."""
        states_file = os.path.join(self.output_dir, "agent_states.csv")
        date_str = self.collective.current_date.strftime("%Y-%m-%d %H:%M:%S")
        
        if self.collective.cpp_engine:
            self.collective.cpp_engine.save_states_csv(
                states_file, 
                date_str, 
                self.first_log_states
            )
        else:
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
        date_str = self.collective.current_date.strftime("%Y-%m-%d %H:%M:%S")
        
        if self.collective.cpp_engine:
            self.collective.cpp_engine.save_interactions_csv(
                interactions_file, 
                date_str, 
                self.first_log_interactions
            )
        else:
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
