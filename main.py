import argparse
import sys
import os
import json

def main():
    parser = argparse.ArgumentParser(description="Движок моделирования коллективного поведения автоматов")
    parser.add_argument("--scenario", type=str, help="Path to scenario JSON file")
    parser.add_argument("--steps", type=int, help="Number of steps to run (overrides scenario)")
    parser.add_argument("--semesters", "-sem", type=int, help="Number of semesters to run (for University mode)")
    parser.add_argument("--silent", "--headless", action="store_true", help="Run in silent mode (no GUI)")
    parser.add_argument("--gui", action="store_true", help="Force GUI mode")
    parser.add_argument("--university", "--uni", action="store_true", help="Launch directly into University map")
    parser.add_argument("--seed", type=int, help="Seed for reproducibility")
    parser.add_argument("--create-scenario", type=str, metavar="PATH", help="Generate a template scenario JSON and exit")
    parser.add_argument("--version", action="version", version="Движок моделирования коллективного поведения автоматов")
    
    args = parser.parse_args()

    # Early exit for scenario creation
    if args.create_scenario:
        from model.simulation_session import SimulationSession
        session = SimulationSession(seed=args.seed)
        session.create_template_scenario(args.create_scenario)
        sys.exit(0)

# Handle University Mode (Robust GUI launch or Headless)
    if args.university:
        print("[System] Loading University Mode...", flush=True)
        is_headless = args.silent or (not args.gui and not sys.stdin.isatty())
        
        if is_headless and args.scenario:
            print("[System] Bypassing GUI (Headless mode active)...", flush=True)
            with open(args.scenario, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            from model.university_collective import UniversityCollective
            from model.simulation_session import SimulationSession
            
            effective_seed = config.get("seed", args.seed)
            univ = UniversityCollective(seed=effective_seed, config=config)
            run_name = config.get("run_name", "Headless University Run")
            description = config.get("description", "")
            scenario_name = config.get("scenario_name", os.path.basename(args.scenario))
            session = SimulationSession(collective=univ, run_name=run_name, description=description, scenario_name=scenario_name)
            
            semesters = args.semesters if args.semesters is not None else config.get("semesters", 8)
            print(f"[System] Headless University Mode: Running {semesters} semesters...", flush=True)
            
            if hasattr(session, 'run_semesters'):
                session.run_semesters(semesters)
            else:
                steps = args.steps if args.steps else config.get("steps", 100)
                for _ in range(steps): session.run_day()
                
            print("Done.", flush=True)
            sys.exit(0)
            
        try:
            import tkinter as tk
            from tkinter import messagebox
            from gui.university_setup_wizard import UniversitySetupWizard
        except ImportError as e:
            print(f"Error: GUI dependencies missing: {e}", file=sys.stderr, flush=True)
            sys.exit(1)

        root = tk.Tk()
        root.title("University Loader")
        root.geometry("1x1+0+0") 
        
        print("[System] Opening Setup Wizard...", flush=True)
        wizard = UniversitySetupWizard(root)
        root.wait_window(wizard)
        
        config = wizard.result_config
        if not config:
            print("[System] Setup cancelled.", flush=True)
            sys.exit(0)

        print("[System] Initializing University Core...", flush=True)
        try:
            from model.university_collective import UniversityCollective
            from model.simulation_session import SimulationSession
            from gui.university_gui import UniversityGUI
            
            # Priority: Wizard/JSON Seed > CLI Argument Seed
            effective_seed = config.get("seed", args.seed)
            univ = UniversityCollective(seed=effective_seed, config=config)
            run_name = config.get("run_name", "Unnamed University Run")
            description = config.get("description", "")
            scenario_name = config.get("scenario_name", "default")
            session = SimulationSession(collective=univ, run_name=run_name, description=description, scenario_name=scenario_name)
            
            if args.steps:
                session.total_steps = args.steps
                
            print("[System] Launching Campus Map...", flush=True)
            app = UniversityGUI(root, univ)
            app.session = session
            root.withdraw()
            
            app.protocol("WM_DELETE_WINDOW", sys.exit)
            app.mainloop()
        except Exception as e:
            import traceback
            error_msg = f"Critical Error:\n{e}\n\n{traceback.format_exc()}"
            print(error_msg, file=sys.stderr, flush=True)
            messagebox.showerror("Fatal Error", error_msg)
            sys.exit(1)
        return

# Standard Simulation Branch
    from model.simulation_session import SimulationSession
    session = SimulationSession(seed=args.seed)
    
    if args.scenario:
        session.load_scenario(args.scenario)
        if args.steps:
            session.total_steps = args.steps

    is_headless = args.silent or (not args.gui and not sys.stdin.isatty())
    
    if is_headless:
        if not args.scenario:
            print("Error: Silent mode requires a scenario file (--scenario).", file=sys.stderr, flush=True)
            sys.exit(1)
        steps = args.steps if args.steps is not None else session.total_steps
        for step in range(steps):
            session.run_day()
        print("Done.", flush=True)
    else:
        from gui.simulation_gui import SimulationGUI
        app = SimulationGUI(session=session)
        app.mainloop()

if __name__ == "__main__":
    main()
