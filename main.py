import argparse
import sys
import os

def main():
    parser = argparse.ArgumentParser(description="Automata Simulation Engine v5.0")
    parser.add_argument("--scenario", type=str, help="Path to scenario JSON file")
    parser.add_argument("--steps", type=int, help="Number of steps to run (overrides scenario)")
    parser.add_argument("--silent", "--headless", action="store_true", help="Run in silent mode (no GUI)")
    parser.add_argument("--gui", action="store_true", help="Force GUI mode")
    parser.add_argument("--university", action="store_true", help="Launch directly into University map")
    parser.add_argument("--create-scenario", type=str, metavar="PATH", help="Generate a template scenario JSON and exit")
    parser.add_argument("--version", action="version", version="Automata Simulation Engine v5.0")
    
    args = parser.parse_args()

    # Defer imports to avoid initializing GUI if not needed
    from model.simulation_session import SimulationSession
    from model.collective import Collective
    from model.university_collective import UniversityCollective
    
    session = SimulationSession()

    if args.create_scenario:
        session.create_template_scenario(args.create_scenario)
        sys.exit(0)

    # If scenario is provided, we use the unified run logic
    if args.scenario:
        if args.silent or (not args.gui and not sys.stdin.isatty()):
            # Headless run from scenario
            session.load_scenario(args.scenario)
            if args.steps:
                session.total_steps = args.steps
                
            if args.university:
                if not isinstance(session.collective, UniversityCollective):
                    # Convert to university
                    univ = UniversityCollective(seed=session.collective.seed)
                    session.reset(new_collective=univ)
            
            steps = args.steps if args.steps is not None else session.total_steps
            print(f"Запуск сценария {os.path.basename(args.scenario)} ({steps} шагов)...", flush=True)
            for step in range(steps):
                session.run_day()
                print(f"Шаг {step+1}/{steps} завершен", flush=True)
        else:
            # GUI run from scenario
            try:
                from gui.simulation_gui import SimulationGUI
                from gui.university_gui import UniversityGUI
            except ImportError:
                print("Error: GUI components not available.", file=sys.stderr)
                sys.exit(1)
                
            session.load_scenario(args.scenario)
            if args.steps:
                session.total_steps = args.steps
            
            if args.university:
                # Force University mode if loading from scenario
                if not isinstance(session.collective, UniversityCollective):
                    print("Warning: Scenario is not a University scenario, but --university was specified. Converting...")
                    univ = UniversityCollective(seed=session.collective.seed)
                    session.reset(new_collective=univ)
                
                app = UniversityGUI(None, session.collective)
                app.session = session # Link session for logging
                # Tk root is needed if we launch it directly
                import tkinter as tk
                root = app.master
                root.withdraw() # Hide the empty root
                app.protocol("WM_DELETE_WINDOW", sys.exit)
                app.mainloop()
            else:
                app = SimulationGUI(session=session)
                app.mainloop()
    else:
        # Default behavior (New World) or manual launch
        if args.silent:
            print("Error: Silent mode requires a scenario file (--scenario).", file=sys.stderr)
            sys.exit(1)
        
        try:
            from gui.simulation_gui import SimulationGUI
            from gui.university_gui import UniversityGUI
        except ImportError:
            print("Error: GUI components not available.", file=sys.stderr)
            sys.exit(1)
            
        if args.university:
            # Direct University Launch without scenario
            univ = UniversityCollective()
            session.reset(new_collective=univ)
            
            # Show map directly
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            app = UniversityGUI(root, univ)
            app.session = session
            app.protocol("WM_DELETE_WINDOW", sys.exit)
            app.mainloop()
        else:
            app = SimulationGUI(session=session)
            app.mainloop()

if __name__ == "__main__":
    main()
