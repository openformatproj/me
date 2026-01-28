def simulate(part, interval_seconds, duration_seconds, scale_factor=1.0, trace_filter=None):
    from ml.event_sources import Timer
    from ml.tracer import Tracer
    from ml.enums import LogLevel, OnFullBehavior
    # Configure Tracer
    Tracer.start(LogLevel.TRACE, 1.0, trace_filter, "logs/simulation_trace.log", "logs/simulation_errors.log")
    
    # Setup Simulation
    part.init()
    timer = Timer('timer', interval_seconds=interval_seconds, duration_seconds=duration_seconds, scale_factor=scale_factor, on_full=OnFullBehavior.DROP)
    
    part.connect_event_source(timer, 'timer_q')
    
    # Run Simulation
    part.start(lambda _: timer.stop_event_is_set())
    timer.start()
    part.wait()
    part.term()
    Tracer.stop()

def view_diagram(part):
    """
    Visualizes the testbench structure using the diagrams tool.
    """
    try:
        from me.serializer import DiagramSerializer
        from diagrams.engine import MainWindow
        from PyQt5.QtWidgets import QApplication
        import sys
    except ImportError as e:
        print(f"Error importing diagram tools: {e}")
        return
    
    # Serialize to JSON
    serializer = DiagramSerializer()
    try:
        json_output = serializer.export_part_to_json(part)
    except Exception as e:
        print(f"Error serializing diagram: {e}")
        return

    # Initialize Qt Application
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    # Create Main Window and load diagram
    main_window = MainWindow(enable_logging=True)
    serializer.import_part_from_json(json_output, main_window)
    
    print("Opening diagram viewer...")
    sys.exit(main_window.start())