import os
from dotenv import load_dotenv
import clickhouse_connect
import uuid
import numpy as np
import datetime
import time

class ClickHouseLogger:
    def __init__(self):
        # Загрузка environment variables from .env if present
        load_dotenv()

        self.user = os.getenv("CLICKHOUSE_USER", "default")
        self.password = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass")
        self.run_id = str(uuid.uuid4())
        self.relations_buffer = [] # Буфер для накопления данных за день
        
        # Попытка 1: Локальный докер (localhost)
        try:
            self.client = clickhouse_connect.get_client(
                host='localhost',
                port=8123,
                username=self.user,
                password=self.password,
                secure=False,
                settings={'insert_deduplicate': 0}
            )
            print(f"ClickHouseLogger: Connected to LOCALHOST (Docker)", flush=True)
        except Exception as e:
            print(f"ClickHouseLogger: Локальный ClickHouse не найден, пробую ТУННЕЛЬ... ({e})", flush=True)
            # Попытка 2: Удаленный туннель
            try:
                self.client = clickhouse_connect.get_client(
                    host='db.georgytadjiev.ink',
                    port=443,
                    username=self.user,
                    password=self.password,
                    secure=True,
                    settings={'insert_deduplicate': 0}
                )
                print(f"ClickHouseLogger: Connected to REMOTE (Cloudflare Tunnel)", flush=True)
            except Exception as e2:
                print(f"КРИТИЧЕСКАЯ ОШИБКА: ClickHouse недоступен ни локально, ни через туннель: {e2}", flush=True)
                self.client = None

    def log_run_metadata(self, run_name: str, description: str, scenario_name: str = "default"):
        """Логирует метаданные (название и описание) симуляции для удобного поиска в БД."""
        if not self.client:
            return
        
        try:
            self.client.insert(
                'simulation_runs',
                [[self.run_id, datetime.datetime.now(), run_name, description, scenario_name]],
                column_names=['run_id', 'start_time', 'run_name', 'description', 'scenario_name']
            )
        except Exception as e:
            print(f"Ошибка при сохранении метаданных симуляции: {e}", flush=True)

    def log_agent_states(self, day_id: int, slot_id: int, engine):
        """
        Извлекает эмоциональные состояния из C++ ядра and сохраняет в agent_states таблицу.
        Векторизованная обработка с использованием библиотеки numpy.
        """
        state = engine.state
        num_agents = state.num_agents
        emotions = np.array(state.emotions, dtype=np.int8).reshape((num_agents, 7))
        
        # Подготовка данных без цикла
        data = list(zip(
            [self.run_id] * num_agents,
            [day_id] * num_agents,
            [slot_id] * num_agents,
            range(num_agents),
            emotions[:, 0].tolist(),
            emotions[:, 1].tolist(),
            emotions[:, 2].tolist(),
            emotions[:, 3].tolist(),
            emotions[:, 4].tolist(),
            emotions[:, 5].tolist(),
            emotions[:, 6].tolist()
        ))
        
        if self.client:
            self.client.insert('agent_states', data, column_names=[
                'run_id', 'day_id', 'slot_id', 'agent_id',
                'sadness_joy', 'fear_calm', 'anger_humility', 'disgust_acceptance',
                'habit_surprise', 'shame_confidence', 'alienation_openness'
            ])

    def log_agent_relations(self, day_id: int, slot_id: int, engine):
        """
        Extracts relations из C++ ядра and сохраняет в БУФЕР (для последующей отправки раз в день).
        """
        state = engine.state
        n = state.num_agents
        relations = np.array(state.relations, dtype=np.int8).reshape((n, n, 3))
        
        ii, jj = np.indices((n, n))
        mask = ii != jj
        
        sub_ids = ii[mask]
        obj_ids = jj[mask]
        rel_values = relations[mask]
        
        num_rows = len(sub_ids)
        
        # Подготовка данных через zip
        data_slot = list(zip(
            [self.run_id] * num_rows,
            [day_id] * num_rows,
            [slot_id] * num_rows,
            sub_ids.tolist(),
            obj_ids.tolist(),
            rel_values[:, 0].tolist(),
            rel_values[:, 1].tolist(),
            rel_values[:, 2].tolist()
        ))
        
        # Добавляем в дневной буфер
        self.relations_buffer.extend(data_slot)

    def flush_day_relations(self):
        """Отправляет накопленные за день отношения в ClickHouse."""
        if not self.client or not self.relations_buffer:
            return
            
        print(f"ClickHouseLogger: Флеш дневного буфера ({len(self.relations_buffer)} записей)...", flush=True)
        
        # Отправляем пачками по 100к (для стабильности даже локально)
        batch_size = 100000
        total_size = len(self.relations_buffer)
        
        for start_idx in range(0, total_size, batch_size):
            end_idx = min(start_idx + batch_size, total_size)
            chunk = self.relations_buffer[start_idx:end_idx]
            self._flush_relations(chunk)
            
        # Очищаем буфер после отправки
        self.relations_buffer = []

    def _flush_relations(self, data):
        if not self.client or not data: return
        try:
            self.client.insert('agent_relations', data, column_names=[
                'run_id', 'day_id', 'slot_id', 'subject_id', 'object_id',
                'utility', 'affinity', 'trust'
            ])
        except Exception as e:
            print(f"Ошибка при вставке отношений (localhost): {e}", flush=True)
            try:
                time.sleep(0.5)
                self.client.insert('agent_relations', data)
            except:
                pass

    def log_interactions(self, day_id: int, slot_id: int, engine, interactions_list=None, name_to_id=None):
        """
        Logs interactions from the last cycle.
        If interactions_list is provided (Python model), logs it.
        Otherwise logs from engine.last_day_interactions (C++ model).
        """
        data = []
        type_map = {'refusal': 0, 'success': 1, 'fail': -1}
        cpp_type_map = {0: 0, 1: 1, 2: -1} # Map C++ enum directly to ClickHouse ints
        
        if interactions_list and name_to_id:
            for from_name, to_name, status in interactions_list:
                # В списке могут быть системные сообщения, игнорируем их
                if from_name not in name_to_id or to_name not in name_to_id:
                    continue
                    
                row = [
                    self.run_id,
                    day_id,
                    slot_id,
                    name_to_id[from_name],
                    name_to_id[to_name],
                    type_map.get(status, 0)
                ]
                data.append(row)
                if len(data) >= 20000:
                    self._flush_interactions(data)
                    data = []
        else:
            # Лог из C++ движка
            for inter in engine.last_day_interactions:
                row = [
                    self.run_id,
                    day_id,
                    slot_id,
                    inter.from_idx,
                    inter.to_idx,
                    cpp_type_map.get(inter.type, 0)
                ]
                data.append(row)
                if len(data) >= 20000:
                    self._flush_interactions(data)
                    data = []
            
        if data:
            self._flush_interactions(data)

    def _flush_interactions(self, data):
        if not self.client: return
        try:
            self.client.insert('interactions', data, column_names=[
                'run_id', 'day_id', 'slot_id', 'from_id', 'to_id', 'type'
            ])
        except Exception as e:
            print(f"Ошибка при вставке взаимодействий в ClickHouse: {e}", flush=True)
            try:
                time.sleep(1)
                self.client.insert('interactions', data, column_names=[
                    'run_id', 'day_id', 'slot_id', 'from_id', 'to_id', 'type'
                ])
            except Exception as e2:
                print(f"Критическая ошибка ClickHouse (Interactions): {e2}", flush=True)

    def log_agent_registry(self, collective):
        """
        Логирует реестр агентов: связывает числовые ID (из C++ ядра) со строковыми ID and метаданными.
        Вызывается один раз в начале симуляции.
        """
        if not self.client: return
        
        data = []
        n = len(collective.agents)
        if hasattr(collective, '_reverse_id_map'):
            for i in range(n):
                string_id = collective._reverse_id_map.get(i)
                if not string_id: continue
                
                agent = collective.agents.get(string_id)
                if not agent: continue
                
                name = getattr(agent, 'name', string_id)
                group_id = getattr(agent, 'group_id', 'Unknown')
                
                arch_enum = getattr(agent.automaton, 'archetype_enum', None)
                archetype = arch_enum.localized if arch_enum else getattr(agent.archetype, 'name', 'Harmony')
                
                row = [
                    self.run_id,
                    i,
                    str(string_id),
                    str(name),
                    str(group_id),
                    str(archetype)
                ]
                data.append(row)
                
            if data:
                self.client.insert('agent_registry', data, column_names=[
                    'run_id', 'agent_id', 'string_id', 'name', 'group_id', 'archetype'
                ])

    def fetch_state(self, target_run_id: str, day_id: int, slot_id: int):
        """
        Retrieves a simulation snapshot from ClickHouse.
        """
        # Получение emotions
        emotions_query = f"""
            SELECT agent_id, sadness_joy, fear_calm, anger_humility, disgust_acceptance, 
                   habit_surprise, shame_confidence, alienation_openness
            FROM agent_states
            WHERE run_id = '{target_run_id}' AND day_id = {day_id} AND slot_id = {slot_id}
            ORDER BY agent_id
        """
        emotions_res = self.client.query(emotions_query)
        
        # Получение relations
        relations_query = f"""
            SELECT ID субъекта, ID объекта, utility, affinity, trust
            FROM agent_relations
            WHERE run_id = '{target_run_id}' AND day_id = {day_id} AND slot_id = {slot_id}
        """
        relations_res = self.client.query(relations_query)
        
        return emotions_res.result_rows, relations_res.result_rows
