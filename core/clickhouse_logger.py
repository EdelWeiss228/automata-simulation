import clickhouse_connect
import uuid
import numpy as np
import datetime

class ClickHouseLogger:
    def __init__(self, host='localhost', port=8123, username='default', password=''):
        self.client = clickhouse_connect.get_client(host=host, port=port, username=username, password=password)
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
                int(emotions[agent_id, 0]), # joy_sadness
                int(emotions[agent_id, 1]), # fear_calm
                int(emotions[agent_id, 2]), # anger_humility
                int(emotions[agent_id, 3]), # disgust_acceptance
                int(emotions[agent_id, 4]), # surprise_habit
                int(emotions[agent_id, 5]), # shame_confidence
                int(emotions[agent_id, 6])  # openness_alienation
            ]
            data.append(row)
        
        self.client.insert('agent_states', data, column_names=[
            'run_id', 'day_id', 'slot_id', 'agent_id',
            'joy_sadness', 'fear_calm', 'anger_humility', 'disgust_acceptance',
            'surprise_habit', 'shame_confidence', 'openness_alienation'
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

    def log_interactions(self, day_id: int, slot_id: int, engine):
        """
        Logs interactions from the last cycle.
        """
        data = []
        type_map = {0: 'refusal', 1: 'success', 2: 'fail'}
        
        for inter in engine.last_day_interactions:
            row = [
                self.run_id,
                day_id,
                slot_id,
                inter.from_idx,
                inter.to_idx,
                type_map.get(inter.type, 'refusal')
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
            SELECT agent_id, joy_sadness, fear_calm, anger_humility, disgust_acceptance, 
                   surprise_habit, shame_confidence, openness_alienation
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
