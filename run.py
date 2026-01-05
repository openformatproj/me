import sys
from functools import partial
# Import the necessary components from the engine library
from PyQt5.QtWidgets import QApplication
from diagrams.engine import MainWindow
from diagrams.optimization import run_simulated_annealing

def open_empty_window():

    # A QApplication instance must be created before any QWidget.
    app = QApplication(sys.argv)

    # --- Configure and Create the Main Window ---

    # # --- Option 1: Randomized Hill Climbing ---
    # from diagrams.optimization import run_randomized_hill_climbing
    # optimizer_params = {
    #     'iterations': 500,
    #     'move_step_grid_units': 10
    # }
    # configured_optimizer = partial(run_randomized_hill_climbing, params=optimizer_params)

    # --- Option 2: Simulated Annealing (Currently Active) ---
    sa_params = {
        'iterations': 1500,
        'initial_temp': 15.0,
        'cooling_rate': 0.996,
        'move_step_grid_units': 15,
        'intersection_weight': 100.0,
        'wirelength_weight': 0.1
    }
    configured_optimizer = partial(run_simulated_annealing, params=sa_params)
    main_window = MainWindow(enable_logging=True, optimizer_func=configured_optimizer)

    # Start the application event loop and exit with its return code.
    sys.exit(main_window.start())

if __name__ == "__main__":
    open_empty_window()