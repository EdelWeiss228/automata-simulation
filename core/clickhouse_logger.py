import os
from dotenv import load_dotenv
import clickhouse_connect
import uuid
import numpy as np
import datetime

class ClickHouseLogger:
    def __init__(self):
        # Load environment variables from .env if present
        load_dotenv()

        self.host = os.getenv("CLICKHOUSE_HOST", "localhost")
        self.port = int(os.getenv("CLICKHOUSE_PORT", 8123))
        self.user = os.getenv("CLICKHOUSE_USER", "default")
        self.password = os.getenv("CLICKHOUSE_PASSWORD", "")
        self.secure = os.getenv("CLICKHOUSE_SECURE", "False").lower() == "true"
        
        try:
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                secure=self.secure,
                settings={'insert_deduplicate': 0}
            )
            print(f"ClickHouseLogger: Connected to {self.host}:{self.port}")
        except Exception as e:
            print(f"Предупреждение: ClickHouse не доступен ({e}). Логирование в БД отключено.")
            self.client = None

        self.run_id = str(uuid.uuid4())

    def log_agent_states(self, day_id: int, slot_id: int, engine):
        """
        Extracts emotions from C++ engine and logs them to agent_states table.
        Emotions vector is flattened N * 7.
        """
        state = engine.state
        num_agents = state.num_agents
        emotions = np.array(state.emotions, dtype=np.int8).reshape((num_agents, 7))
        
        data = []
        for agent_id in range(num_agents):
            row = [
                self.run_id,
                day_id,
                slot_id,
                agent_id,
                int(emotions[agent_id, 0]), # sadness_joy
                int(emotions[agent_id, 1]), # fear_calm
                int(emotions[agent_id, 2]), # anger_humility
                int(emotions[agent_id, 3]), # disgust_acceptance
                int(emotions[agent_id, 4]), # habit_surprise
                int(emotions[agent_id, 5]), # shame_confidence
                int(emotions[agent_id, 6])  # alienation_openness
            ]
            data.append(row)
        
        self.client.insert('agent_states', data, column_names=[
            'run_id', 'day_id', 'slot_id', 'agent_id',
            'sadness_joy', 'fear_calm', 'anger_humility', 'disgust_acceptance',
            'habit_surprise', 'shame_confidence', 'alienation_openness'
        ])

    def log_agent_relations(self, day_id: int, slot_id: int, engine):
        """
        Extracts relations from C++ engine and logs them to agent_relations table.
        Relations vector is flattened N * N * 3.
        """
        state = engine.state
        n = state.num_agents
        # relations mapping: (i * n + j) * 3 + [0:U, 1:A, 2:T]
        relations = np.array(state.relations, dtype=np.int8).reshape((n, n, 3))
        
        data = []
        for i in range(n):
            for j in range(n):
                if i == j: continue  # Skip self-relations if not needed, but prompt didn't specify
                row = [
                    self.run_id,
                    day_id,
                    slot_id,
                    i, # subject_id
                    j, # object_id
                    int(relations[i, j, 0]), # utility
                    int(relations[i, j, 1]), # affinity
                    int(relations[i, j, 2])  # trust
                ]
                data.append(row)
                
                # Batch insert if data gets too large to save memory
                if len(data) >= 100000:
                    self._flush_relations(data)
                    data = []
        
        if data:
            self._flush_relations(data)

    def _flush_relations(self, data):
        self.client.insert('agent_relations', data, column_names=[
            'run_id', 'day_id', 'slot_id', 'subject_id', 'object_id',
            'utility', 'affinity', 'trust'
        ])

    def log_interactions(self, day_id: int, slot_id: int, engine, interactions_list=None, name_to_id=None):
        """
        Logs interactions from the last cycle.
        If interactions_list is provided (Python model), logs it.
        Otherwise logs from engine.last_day_interactions (C++ model).
        """
        data = []
        type_map = {'refusal': 0, 'success': 1, 'fail': -1}
        cpp_type_map = {0: 'refusal', 1: 'success', 2: 'fail'} # Not changed yet to avoid C++ breaking, but logic will use type_map
        
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
                    status if status in type_map else 'refusal'
                ]
                data.append(row)
        else:
            # Лог из C++ движка
            for inter in engine.last_day_interactions:
                row = [
                    self.run_id,
                    day_id,
                    slot_id,
                    inter.from_idx,
                    inter.to_idx,
                    cpp_type_map.get(inter.type, 'refusal')
                ]
                data.append(row)
            
        if data:
            self.client.insert('interactions', data, column_names=[
                'run_id', 'day_id', 'slot_id', 'from_id', 'to_id', 'type'
            ])

    def fetch_state(self, target_run_id: str, day_id: int, slot_id: int):
        """
        Retrieves a simulation snapshot from ClickHouse.
        """
        # Fetch emotions
        emotions_query = f"""
            SELECT agent_id, sadness_joy, fear_calm, anger_humility, disgust_acceptance, 
                   habit_surprise, shame_confidence, alienation_openness
            FROM agent_states
            WHERE run_id = '{target_run_id}' AND day_id = {day_id} AND slot_id = {slot_id}
            ORDER BY agent_id
        """
        emotions_res = self.client.query(emotions_query)
        
        # Fetch relations
        relations_query = f"""
            SELECT subject_id, object_id, utility, affinity, trust
            FROM agent_relations
            WHERE run_id = '{target_run_id}' AND day_id = {day_id} AND slot_id = {slot_id}
        """
        relations_res = self.client.query(relations_query)
        
        return emotions_res.result_rows, relations_res.result_rows
