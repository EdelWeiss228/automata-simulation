import os
import datetime
from model.collective import Collective
from core.data_logger import DataLogger
try:
    from core.clickhouse_logger import ClickHouseLogger
except ImportError:
    ClickHouseLogger = None

class SimulationSession:
    """
    Класс, инкапсулирующий логику сессии симуляции.
    Отвечает за управление коллективом, шаги времени и сохранение данных.
    """
    def __init__(self, collective=None, output_dir="data/output"):
        self.collective = collective if collective else Collective()
        self.logger = DataLogger()
        self.ch_logger = None
        if ClickHouseLogger:
            try:
                self.ch_logger = ClickHouseLogger()
            except Exception as e:
                print(f"Предупреждение: ClickHouse не доступен ({e}). Логирование в БД отключено.")
        
        self.run_id = self.ch_logger.run_id if self.ch_logger else None
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
        
        seed = scenario.get("seed")
        self.reset(seed=seed)
        
        agents = generate_research_agents(scenario)
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

    def load_state_from_clickhouse(self, run_id, day_id, slot_id=0):
        """
        Загружает состояние симуляции из ClickHouse (Time-Travel).
        """
        if not self.ch_logger:
            print("Ошибка: ClickHouseLogger не инициализирован.")
            return False
            
        print(f"Загрузка состояния: run={run_id}, day={day_id}, slot={slot_id}...")
        emotions, relations = self.ch_logger.fetch_state(run_id, day_id, slot_id)
        
        if not self.collective.cpp_engine:
            import emotion_engine
            self.collective.cpp_engine = emotion_engine.Engine(len(self.collective.agents))
            
        engine = self.collective.cpp_engine
        
        # Инъекция эмоций
        for row in emotions:
            agent_id = row[0]
            for axis in range(7):
                engine.set_emotion(agent_id, axis, row[axis + 1])
                
        # Инъекция отношений
        for row in relations:
            u_id, o_id, util, aff, trust = row
            engine.set_relation(u_id, o_id, util, aff, trust)
            
        # Синхронизация Python-объектов
        self.collective._sync_from_cpp(sync_relations=True)
        self.simulation_started = True
        print("Состояние успешно восстановлено.")
        return True

    def run_day(self):
        """Выполняет один цикл симуляции дня и логирует результаты."""
        # Начальный лог состояний перед первым шагом
        if not self.simulation_started:
            self.collective._sync_to_cpp()
            self.log_states(slot_id=0)
            self.simulation_started = True

        all_interactions = []
        is_headless = not hasattr(self, 'gui_active') or not self.gui_active 

        if hasattr(self.collective, 'day_schedule_slots'):
            while True:
                interactions = self.collective.perform_next_step()
                
                # Проверяем, не является ли этот шаг просто техническим переходом дня
                is_day_ready = any(res == "New_Day_Ready" for _, _, res in interactions if isinstance(res, str))
                
                if not is_day_ready:
                    all_interactions.extend(interactions)
                    
                    # ОБЯЗАТЕЛЬНАЯ СИНХРОНИЗАЦИЯ: Университет работает на Python,
                    # но логгер ClickHouse читает из C++. Синкаем перед логированием.
                    if self.collective.cpp_engine:
                        self.collective._sync_to_cpp()

                    # slot_id отражает состояние ПОСЛЕ совершения шага (1..9)
                    slot_id = self.collective.current_slot_idx
                    self.log_interactions(interactions, slot_id=slot_id)
                    self.log_states(slot_id=slot_id)
                else:
                    break
        else:
            # Обычный режим (один большой шаг)
            all_interactions = self.collective.perform_full_day_cycle(interactive=False)
            self.log_interactions(all_interactions, slot_id=1)
            self.log_states(slot_id=1)

        # Синхронизация для GUI (если нужно)
        if not is_headless:
            self.collective._sync_from_cpp(sync_relations=True)
        elif self.collective.cpp_engine:
            self.collective._sync_from_cpp(sync_relations=False)

        return all_interactions

    def log_states(self, slot_id=0):
        """Записывает текущие состояния агентов в файл."""
        states_file = os.path.join(self.output_dir, "agent_states.csv")
        date_str = self.collective.current_date.strftime("%Y-%m-%d %H:%M:%S")
        
        if self.collective.cpp_engine:
            if self.ch_logger:
                # В ClickHouse логируем каждое изменение
                self.ch_logger.log_agent_states(self.collective.current_step, slot_id, self.collective.cpp_engine)
                # Логируем отношения
                self.ch_logger.log_agent_relations(self.collective.current_step, slot_id, self.collective.cpp_engine)
            else:
                # Фоллбек: пишем в CSV каждый шаг, раз ClickHouse не доступен
                self.collective.cpp_engine.save_states_csv(
                    states_file, 
                    date_str, 
                    self.first_log_states
                )
                self.first_log_states = False
        else:
            self.logger.log_agent_states(
                states_file, 
                self.collective.current_date, 
                self.collective.agents, 
                self.first_log_states
            )
            self.first_log_states = False

    def log_interactions(self, interactions, slot_id=0):
        """Записывает взаимодействия за день в файл."""
        interactions_file = os.path.join(self.output_dir, "interaction_log.csv")
        date_str = self.collective.current_date.strftime("%Y-%m-%d %H:%M:%S")
        
        if self.collective.cpp_engine:
            if self.ch_logger:
                # В ClickHouse логируем каждое изменение
                self.ch_logger.log_interactions(
                    self.collective.current_step, 
                    slot_id, 
                    self.collective.cpp_engine,
                    interactions_list=interactions,
                    name_to_id=getattr(self.collective, '_id_map', None)
                )
            else:
                # Фоллбек: пишем в CSV каждый шаг
                self.collective.cpp_engine.save_interactions_csv(
                    interactions_file, 
                    date_str, 
                    self.first_log_interactions
                )
                self.first_log_interactions = False
        else:
            self.logger.log_interactions(
                interactions_file, 
                self.collective.current_date, 
                interactions, 
                self.first_log_interactions
            )
            self.first_log_interactions = False

    def reset(self, new_collective=None, seed=None):
        """Сбрасывает сессию симуляции."""
        if new_collective:
            self.collective = new_collective
        else:
            self.collective = Collective(seed=seed)
        self.first_log_states = True
        self.first_log_interactions = True
        self.simulation_started = False
        os.makedirs(self.output_dir, exist_ok=True)
