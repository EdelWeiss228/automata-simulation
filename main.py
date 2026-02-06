from gui.simulation_gui import SimulationGUI
from model.simulation_session import SimulationSession

if __name__ == "__main__":
    session = SimulationSession()
    app = SimulationGUI(session=session)
    app.mainloop()
