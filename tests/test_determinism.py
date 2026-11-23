import hashlib
import os
import random
import subprocess
import sys
import textwrap
import unittest
from datetime import date

from model.university_collective import UniversityCollective


ENGINE_SCRIPT = textwrap.dedent(
    """
    import hashlib
    import os
    import random
    import sys

    sys.path.insert(0, os.path.join(os.getcwd(), "core"))
    import emotion_engine

    n = int(sys.argv[1])
    cycles = int(sys.argv[2])
    engine = emotion_engine.Engine(n)
    rng = random.Random(12345)
    engine.state.emotions = [rng.randint(-30, 30) for _ in range(n * 7)]
    engine.state.relations = [rng.randint(-100, 100) for _ in range(n * n * 3)]
    engine.state.sensitivities = [rng.uniform(0.1, 3.0) for _ in range(n)]
    engine.state.agent_archetypes = [rng.randrange(9) for _ in range(n)]
    for i in range(9):
        engine.set_archetype_config(
            i, 0.3, 8.0, 1.0, 2.0, i % 3, [10.0] * 7,
            "linear", "linear", "linear",
        )
    engine.seed(12345)
    for _ in range(cycles):
        engine.perform_daily_cycle(1)

    digest = hashlib.sha256()
    digest.update(bytes(str(engine.state.emotions), "ascii"))
    digest.update(bytes(str(engine.state.relations), "ascii"))
    digest.update(bytes(str(
        [(x.from_idx, x.to_idx, x.type) for x in engine.last_day_interactions]
    ), "ascii"))
    print(digest.hexdigest())
    """
)


class EngineDeterminismTest(unittest.TestCase):
    def _hash(self, n, cycles, threads):
        env = dict(os.environ)
        env["OMP_NUM_THREADS"] = str(threads)
        proc = subprocess.run(
            [sys.executable, "-c", ENGINE_SCRIPT, str(n), str(cycles)],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip()

    def test_openmp_threads_do_not_change_state(self):
        for n, cycles in ((100, 2), (400, 1)):
            hashes = {
                threads: self._hash(n, cycles, threads)
                for threads in (1, 2, 8)
            }
            self.assertEqual(len(set(hashes.values())), 1, msg=f"N={n}: {hashes}")


def simulation_hash(collective):
    digest = hashlib.sha256()
    for agent_id in sorted(collective.agents):
        agent = collective.agents[agent_id]
        digest.update(bytes(str(tuple(agent.emotion_vector)), "ascii"))
        for target_id in sorted(collective.agents):
            if target_id == agent_id:
                continue
            rel = agent.relations[target_id]
            digest.update(bytes(str((
                rel["utility"], rel["affinity"], rel["trust"]
            )), "ascii"))
    return digest.hexdigest()


class SimulationDeterminismTest(unittest.TestCase):
    def test_same_seed_same_two_days(self):
        def run():
            random.seed(2024)
            c = UniversityCollective(
                seed=2024,
                config={
                    "start_year": 2024,
                    "initial_relations_mode": "EMPTY",
                    "total_bac": 100,
                    "total_mag": 12,
                },
            )
            c.current_date = date(2024, 9, 2)  # Monday
            for _ in range(2):
                c.perform_full_day_cycle()
            return simulation_hash(c)

        self.assertEqual(run(), run())


if __name__ == "__main__":
    unittest.main()
