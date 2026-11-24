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
        self.host = os.getenv("CLICKHOUSE_HOST", "localhost")
        self.port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
        self.secure = os.getenv("CLICKHOUSE_SECURE", "False").lower() in ("true", "1", "yes")
        
        # Буфер дневных отношений. Хранит столбцовые пакеты, а не 2.6M
        # Python-кортежей: при N=1620 разница по памяти — сотни мегабайт.
        self.relations_buffer = []
        self._timings_table_ready = False
        
        try:
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                secure=self.secure,
                settings={'insert_deduplicate': 0}
            )
            print(f"ClickHouseLogger: Успешно подключено к ClickHouse ({self.host}:{self.port})", flush=True)
        except Exception as e:
            print(f"ПРЕДУПРЕЖДЕНИЕ: СУБД ClickHouse недоступна по адресу {self.host}:{self.port} ({e}). Логирование в БД будет отключено.", flush=True)
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

    def _ensure_timings_table(self):
        """Создать run_timings на существующей базе без ручной миграции."""
        if self._timings_table_ready or not self.client:
            return
        self.client.command("""
            CREATE TABLE IF NOT EXISTS run_timings (
                run_id UUID,
                scenario String,
                implementation LowCardinality(String),
                engine LowCardinality(String),
                version String,
                started_at DateTime64(3),
                finished_at DateTime64(3),
                wall_seconds Float64,
                cpu_user_seconds Float64,
                cpu_system_seconds Float64,
                max_rss_kb UInt64,
                init_seconds Float64,
                simulation_seconds Float64,
                finalize_seconds Float64,
                agents UInt32,
                days UInt32,
                semesters UInt8,
                interactions UInt64,
                seed Int64,
                status LowCardinality(String),
                platform String,
                python_version String,
                omp_threads String,
                workers String
            ) ENGINE = MergeTree
            ORDER BY (implementation, started_at, run_id)
        """)
        self._timings_table_ready = True

    def log_run_timing(self, payload: dict):
        """Сохранить метрики скорости прогона для сравнения реализаций."""
        if not self.client:
            return
        run_id = payload.get("run_id")
        if not run_id:
            # Ошибка до создания run_id: остаётся только JSON-файл.
            return

        def _dt(value):
            if not value:
                return datetime.datetime.now()
            parsed = datetime.datetime.fromisoformat(str(value))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return parsed

        try:
            self._ensure_timings_table()
            row = [
                str(run_id),
                str(payload.get("scenario", "")),
                str(payload.get("implementation", "")),
                str(payload.get("engine", "")),
                str(payload.get("version", "")),
                _dt(payload.get("started_at")),
                _dt(payload.get("finished_at")),
                float(payload.get("wall_seconds", 0.0)),
                float(payload.get("cpu_user_seconds", 0.0)),
                float(payload.get("cpu_system_seconds", 0.0)),
                int(payload.get("max_rss_kb", 0)),
                float(payload.get("init_seconds", 0.0)),
                float(payload.get("simulation_seconds", 0.0)),
                float(payload.get("finalize_seconds", 0.0)),
                int(payload.get("agents", 0)),
                int(payload.get("days", 0)),
                int(payload.get("semesters", 0)),
                int(payload.get("interactions", 0)),
                int(payload.get("seed") or 0),
                str(payload.get("status", "")),
                str(payload.get("platform", "")),
                str(payload.get("python_version", "")),
                str(payload.get("omp_threads", "")),
                str(payload.get("workers", "")),
            ]
            self.client.insert(
                'run_timings',
                [row],
                column_names=[
                    'run_id', 'scenario', 'implementation', 'engine', 'version',
                    'started_at', 'finished_at', 'wall_seconds',
                    'cpu_user_seconds', 'cpu_system_seconds', 'max_rss_kb',
                    'init_seconds', 'simulation_seconds', 'finalize_seconds',
                    'agents', 'days', 'semesters', 'interactions', 'seed',
                    'status', 'platform', 'python_version', 'omp_threads',
                    'workers',
                ],
            )
        except Exception as e:
            print(f"Ошибка при сохранении таймингов прогона: {e}", flush=True)

    def log_agent_states(self, day_id: int, slot_id: int, engine, collective=None):
        """
        Извлекает эмоциональные состояния из C++ ядра and сохраняет в agent_states таблицу.
        Векторизованная обработка с использованием библиотеки numpy.
        """
        state = engine.state
        num_agents = state.num_agents
        emotions = np.array(state.emotions, dtype=np.int8).reshape((num_agents, 7))
        # Постоянные ID людей: индексы C++ меняются после ротации, а
        # человек должен оставаться одним и тем же agent_id.
        if collective is not None:
            stable_ids = collective.stable_ids_for_engine()
            if len(stable_ids) != num_agents:
                raise ValueError(
                    f"stable_id map has {len(stable_ids)} entries, "
                    f"engine has {num_agents} agents"
                )
            agent_ids = stable_ids.tolist()
        else:
            agent_ids = list(range(num_agents))
        
        # Подготовка данных без цикла
        data = list(zip(
            [self.run_id] * num_agents,
            [day_id] * num_agents,
            [slot_id] * num_agents,
            agent_ids,
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

    def log_agent_relations(self, day_id: int, slot_id: int, engine, collective=None):
        """
        Извлекает отношения из C++ ядра и складывает столбцовый пакет в буфер.
        """
        if not self.client:
            return

        state = engine.state
        n = state.num_agents
        relations = np.array(state.relations, dtype=np.int8).reshape((n, n, 3))
        if collective is not None:
            stable_ids = collective.stable_ids_for_engine()
            if len(stable_ids) != n:
                raise ValueError(
                    f"stable_id map has {len(stable_ids)} entries, "
                    f"engine has {n} agents"
                )
        else:
            stable_ids = np.arange(n, dtype=np.uint32)

        ii, jj = np.indices((n, n))
        # Нулевая связь — это tabula rasa, а не «нейтральное отношение».
        # Полная матрица 1620x1620 давала 2.6 млн строк в день и десятки
        # миллиардов строк за матрицу 42 прогонов. Храним только реально
        # существующие связи; отсутствие строки означает ноль.
        mask = (ii != jj) & np.any(relations != 0, axis=2)

        sub_ids = stable_ids[ii[mask]].astype(np.uint32)
        obj_ids = stable_ids[jj[mask]].astype(np.uint32)
        rel_values = relations[mask]
        num_rows = len(sub_ids)

        run_ids = np.empty(num_rows, dtype=object)
        run_ids[:] = self.run_id
        day_ids = np.full(num_rows, day_id, dtype=np.uint32)
        slot_ids = np.full(num_rows, slot_id, dtype=np.uint8)

        self.relations_buffer.append((
            run_ids,
            day_ids,
            slot_ids,
            sub_ids,
            obj_ids,
            rel_values[:, 0],
            rel_values[:, 1],
            rel_values[:, 2],
        ))

    def flush_day_relations(self):
        """Отправляет накопленные за день отношения в ClickHouse."""
        if not self.client or not self.relations_buffer:
            return

        total_size = sum(len(chunk[0]) for chunk in self.relations_buffer)
        print(f"ClickHouseLogger: Флеш дневного буфера ({total_size} записей)...", flush=True)

        for chunk in self.relations_buffer:
            self._flush_relations(chunk)

        # Очищаем буфер после отправки
        self.relations_buffer = []

    def _flush_relations(self, data):
        if not self.client or not data: return
        columns = [
            'run_id', 'day_id', 'slot_id', 'subject_id', 'object_id',
            'utility', 'affinity', 'trust'
        ]
        try:
            self.client.insert(
                'agent_relations', data,
                column_names=columns, column_oriented=True
            )
        except Exception as e:
            print(f"Ошибка при вставке отношений (localhost): {e}", flush=True)
            try:
                time.sleep(0.5)
                self.client.insert(
                    'agent_relations', data,
                    column_names=columns, column_oriented=True
                )
            except Exception as e2:
                print(f"Критическая ошибка ClickHouse (Relations): {e2}", flush=True)

    def log_interactions(self, day_id: int, slot_id: int, engine, interactions_list=None, name_to_id=None, id_offset=0, stable_id_map=None, collective=None):
        """
        Logs interactions from the last cycle.
        If interactions_list is provided (Python model), logs it.
        Otherwise logs from engine.last_day_interactions (C++ model).
        """
        data = []
        type_map = {'refusal': 0, 'success': 1, 'fail': -1}
        # C++ уже пишет -1/0/1, как и Python Outcome.
        cpp_type_map = {-1: -1, 0: 0, 1: 1}
        
        # Пустой список — это «в этом слоте никто не общался», а не
        # повод логировать last_day_interactions из C++-ядра.
        if interactions_list is not None and (
            stable_id_map is not None or name_to_id is not None
        ):
            mapping = stable_id_map if stable_id_map is not None else name_to_id
            extra = 0 if stable_id_map is not None else id_offset
            for from_name, to_name, status in interactions_list:
                # В списке могут быть системные сообщения, игнорируем их
                if from_name not in mapping or to_name not in mapping:
                    continue
                    
                row = [
                    self.run_id,
                    day_id,
                    slot_id,
                    mapping[from_name] + extra,
                    mapping[to_name] + extra,
                    type_map.get(status, 0)
                ]
                data.append(row)
                if len(data) >= 20000:
                    self._flush_interactions(data)
                    data = []
        else:
            # Лог из C++ движка
            stable_ids = None
            if collective is not None:
                stable_ids = collective.stable_ids_for_engine()
            for inter in engine.last_day_interactions:
                from_id = (
                    int(stable_ids[inter.from_idx])
                    if stable_ids is not None else inter.from_idx + id_offset
                )
                to_id = (
                    int(stable_ids[inter.to_idx])
                    if stable_ids is not None else inter.to_idx + id_offset
                )
                row = [
                    self.run_id,
                    day_id,
                    slot_id,
                    from_id,
                    to_id,
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
        Дописывает реестр агентов. Вызывается в начале прогона и после
        академической ротации, когда появляются новые люди. Один человек
        получает одну строку на весь прогон: постоянный stable_id.
        """
        if not self.client:
            return
        if not hasattr(self, '_logged_registry_ids'):
            self._logged_registry_ids = set()

        data = []
        for agent in collective.agents.values():
            stable_id = collective._ensure_stable_id(agent)
            if stable_id in self._logged_registry_ids:
                continue
            name = getattr(agent, 'name', agent.id)
            group_id = getattr(agent, 'group_id', 'Unknown')

            arch_enum = getattr(agent.automaton, 'archetype_enum', None)
            archetype = (
                arch_enum.localized if arch_enum
                else getattr(agent.archetype, 'name', 'Harmony')
            )

            data.append([
                self.run_id,
                stable_id,
                str(agent.id),
                str(name),
                str(group_id),
                str(archetype),
            ])
            self._logged_registry_ids.add(stable_id)

        if data:
            self.client.insert('agent_registry', data, column_names=[
                'run_id', 'agent_id', 'string_id', 'name', 'group_id', 'archetype'
            ])

    def fetch_registry(self, target_run_id: str):
        """Возвращает agent_id -> string_id для восстановления снимка."""
        result = self.client.query(
            "SELECT agent_id, string_id FROM agent_registry "
            f"WHERE run_id = '{target_run_id}'"
        )
        return {int(row[0]): str(row[1]) for row in result.result_rows}

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
            SELECT subject_id, object_id, utility, affinity, trust
            FROM agent_relations
            WHERE run_id = '{target_run_id}' AND day_id = {day_id} AND slot_id = {slot_id}
        """
        relations_res = self.client.query(relations_query)
        
        return emotions_res.result_rows, relations_res.result_rows
