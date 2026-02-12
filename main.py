import argparse
import sys
import os

def main():
    parser = argparse.ArgumentParser(description="Automata Simulation Engine v5.0")
    parser.add_argument("--scenario", type=str, help="Path to scenario JSON file")
    parser.add_argument("--steps", type=int, help="Number of steps to run (overrides scenario)")
    parser.add_argument("--silent", "--headless", action="store_true", help="Run in silent mode (no GUI)")
    parser.add_argument("--gui", action="store_true", help="Force GUI mode")
    parser.add_argument("--create-scenario", type=str, metavar="PATH", help="Generate a template scenario JSON and exit")
    parser.add_argument("--version", action="version", version="Automata Simulation Engine v5.0")
    
    args = parser.parse_args()

    # Defer imports to avoid initializing GUI if not needed
    from model.simulation_session import SimulationSession
    
    session = SimulationSession()

    if args.create_scenario:
        session.create_template_scenario(args.create_scenario)
        sys.exit(0)

    # If scenario is provided, we use the unified run logic
    if args.scenario:
        if args.silent or (not args.gui and not sys.stdin.isatty()):
            # Headless run from scenario
            session.run_scenario(args.scenario, override_steps=args.steps)
        else:
            # GUI run from scenario
            try:
                from gui.simulation_gui import SimulationGUI
            except ImportError:
                print("Error: GUI components not available.", file=sys.stderr)
                sys.exit(1)
                
            session.load_scenario(args.scenario)
            if args.steps:
                session.total_steps = args.steps
            app = SimulationGUI(session=session)
            app.mainloop()
    else:
        # Default behavior (New World) or manual launch
        if args.silent:
            print("Error: Silent mode requires a scenario file (--scenario).", file=sys.stderr)
            sys.exit(1)
        
        try:
            from gui.simulation_gui import SimulationGUI
        except ImportError:
            print("Error: GUI components not available.", file=sys.stderr)
            sys.exit(1)
            
        app = SimulationGUI(session=session)
        app.mainloop()

if __name__ == "__main__":
    main()
