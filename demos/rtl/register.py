from ml.engine import Part, Port, EventQueue
from ml.strategies import Execution
from ml.strategies import all_updated
from me.domains.hardware.digital import Logic, rising_edge, generate_code
from me.parts.hardware.digital import vcd_monitor

class Register(Part):
    """
    A part that behaves like a simple register, updating out_0 with in_0
    whenever the clock port is updated.
    """
    def __init__(self, identifier: str):
        ports = [
            Port('clk', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('rst', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('in_0', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('out_0', Port.OUT, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT)
        ]
        super().__init__(identifier=identifier, ports=ports, scheduling_condition=all_updated, scheduling_args=('clk',))

    @rising_edge('clk')
    def behavior(self):
        if self.read('rst') == Logic.ONE:
            self.write('out_0', Logic.ZERO)
        else:
            self.write('out_0', self.read('in_0'))

class Clock(Part):
    """
    Docstring for Clock
    """
    def __init__(self, identifier: str):
        ports = [
            Port('clk', Port.OUT, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('time_port', Port.OUT, type=float)
        ]
        event_queues = [EventQueue('time', EventQueue.IN, size=1)]
        super().__init__(identifier=identifier, ports=ports, event_queues=event_queues)
        self.state = Logic.U

    def behavior(self):
        event_queue = self.get_event_queue('time')
        if not event_queue.is_empty():
            t = event_queue.pop()
            self.write('time_port', t)
            if self.state == Logic.U:
                state = Logic.ZERO
            else:
                state = ~self.state
            self.write('clk', state)
            self.trace_log(f"Clock@time {t} -> Drive clock {self.state} -> {state}")
            self.state = state

class Source(Part):
    """
    Generates clock, reset, and input signals for the DUT.
    """
    def __init__(self, identifier: str):
        ports = [
            Port('clk', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('rst', Port.OUT, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('out_0', Port.OUT, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
        ]
        super().__init__(identifier, ports=ports, scheduling_condition=all_updated, scheduling_args=('clk',))
        self.cycle = 0

    @rising_edge('clk')
    def behavior(self):

        # Assert reset for the first few cycles
        if self.cycle < 5:
            self.write('rst', Logic.ONE)
        else:
            self.write('rst', Logic.ZERO)

        # Change input data periodically
        if self.cycle % 4 == 0:
            self.write('out_0', Logic.ONE)
        else:
            self.write('out_0', Logic.ZERO)

        self.trace_log(f"Source@cycle {self.cycle} -> Drive rst={self.get_port('rst').peek().value}, out_0={self.get_port('out_0').peek().value}")
        self.cycle += 1

class Sink(Part):
    """
    Consumes the output from the DUT to prevent OverwriteError and verify behavior.
    """
    def __init__(self, identifier: str):
        ports = [
            Port('in_0', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT)
        ]
        super().__init__(identifier, ports=ports)

    def behavior(self):
        self.trace_log(f"Sink -> Receive = {self.read('in_0').value}")

@vcd_monitor('logs/waveforms.vcd', {
    'clock.clk': 'clock.clk',
    'source.rst': 'source.rst',
    'dut.in_0': 'source.out_0',
    'dut.out_0': 'dut.out_0'
}, time_path='clock.time_port')
class Testbench(Part):

    def __init__(self, identifier: str):
        event_queues = [EventQueue('timer_q', EventQueue.IN, size=1)]
        
        parts = {
            'clock': Clock('clock'),
            'source': Source('source'),
            'dut': Register('dut'),
            'sink': Sink('sink')
        }
        
        super().__init__(identifier, parts=parts, event_queues=event_queues, execution_strategy=Execution.sequential())
        
        # Wire the Timer event to the Clock
        self.wire_event('timer_q', 'clock.time')
        
        # Wire Clock to Source and DUT
        self.wire('clock.clk', 'source.clk')
        self.wire('clock.clk', 'dut.clk')
        
        # Wire Source signals to DUT
        self.wire('source.rst', 'dut.rst')
        self.wire('source.out_0', 'dut.in_0')
        
        # Wire DUT output to Sink
        self.wire('dut.out_0', 'sink.in_0')

def generate_vhdl_code(llm):
    import os
    import sys
    
    if llm:

        try:
            from google import genai
            from google.genai import errors
        except ImportError:
            print("Error: 'google-genai' library not found. Please run: pip install google-genai")
            return
        
        import time

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable is not set.")
            return

        client = genai.Client(api_key=api_key)
        model="gemini-2.5-flash-lite"

        def gemini_client(prompt: str) -> str:
            retries = 3
            while retries > 0:
                try:
                    response = client.models.generate_content(model=model, contents=prompt)
                    # Clean up Markdown code fences if the model returns them
                    text = response.text.replace("```vhdl", "").replace("```", "").strip()
                    return f"-- Generated by {model}\n{text}"
                except errors.ClientError as e:
                    if e.code == 429:
                        print("Quota exceeded (429). Retrying in 35 seconds...")
                        time.sleep(35)
                        retries -= 1
                    elif e.code == 404:
                        print(f"Error: Model '{model}' not found. Please verify the model name.")
                        print("Available models:")
                        try:
                            for m in client.models.list():
                                print(f" - {m.name}")
                        except Exception as list_e:
                            print(f"Failed to list models: {list_e}")
                        sys.exit(0)
                    else:
                        raise e
            raise Exception("Gemini API quota exceeded after retries.")
        
        llm_client = gemini_client
    
    else:

        llm_client = None

    try:
        vhdl_code = generate_code(Register('dut'), language="VHDL", entity_name="register", architecture_name="rtl", llm_client=llm_client)
    except Exception as e:
        raise Exception(f"VHDL generation failed: {e}")

    output_dir = "gen"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    filename = os.path.join(output_dir, "register.vhd")
    with open(filename, "w") as f:
        f.write(vhdl_code)
    print(f"VHDL code generated in {filename}")

def view_testbench_diagram():
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

    # Instantiate the testbench
    # Note: The vcd_monitor decorator will automatically add the VCDMonitor part.
    tb = Testbench('tb')
    
    # Serialize to JSON
    serializer = DiagramSerializer()
    try:
        json_output = serializer.export_part_to_json(tb)
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

def simulate():
    from ml.event_sources import Timer
    from ml.tracer import Tracer
    from ml.enums import LogLevel, OnFullBehavior
    # Configure Tracer
    Tracer.start(LogLevel.INFO, 1.0, "logs/simulation_trace.log", "logs/simulation_errors.log")
    
    # Setup Simulation
    tb = Testbench('tb')
    tb.init()
    # The timer drives the clock toggling. interval_seconds=0.1 -> 100 ms, clock period: 200 ms
    timer = Timer('timer', interval_seconds=0.1, duration_seconds=3.0, on_full=OnFullBehavior.DROP)
    
    tb.connect_event_source(timer, 'timer_q')
    
    # Run Simulation
    tb.start(lambda _: timer.stop_event_is_set())
    timer.start()
    tb.wait()
    tb.term()
    Tracer.stop()

if __name__ == "__main__":
    simulate()
    # view_testbench_diagram()
    # generate_vhdl_code(llm=True)