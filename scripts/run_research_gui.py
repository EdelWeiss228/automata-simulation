import argparse
import sys
import os

# Добавляем корневую директорию проекта в path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from model.simulation_session import SimulationSession

def main():
    parser = argparse.ArgumentParser(description="GUI Research Runner v5.0")
    parser.add_argument("scenario", type=str, help="Path to scenario JSON file")
    parser.add_argument("--steps", type=int, help="Number of steps (overrides scenario)")
    parser.add_argument("--gui", action="store_true", default=True, help="Run in GUI mode (default)")
    
    args = parser.parse_args()

    if not os.path.exists(args.scenario):
        print(f"Error: Scenario file '{args.scenario}' not found.", file=sys.stderr)
        sys.exit(1)

    from gui.simulation_gui import SimulationGUI
    
    session = SimulationSession()
    session.load_scenario(args.scenario)
    if args.steps:
        session.total_steps = args.steps
        
    app = SimulationGUI(session=session)
    app.title(f"Research Mode: Scenario Loading...")
    app.mainloop()

if __name__ == "__main__":
    main()
