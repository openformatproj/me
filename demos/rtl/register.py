from ml.engine import Part, Port, EventQueue
from ml.strategies import Execution
from ml.strategies import all_updated
from me.domains.hardware.digital import Logic, rising_edge, generate_code
from me.parts.hardware.digital import Clock, vcd_monitor
from me.services import view_diagram, simulate

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

class Source(Part):
    """
    Generates reset and input signals for the DUT.
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

if __name__ == "__main__":
    simulate(Testbench('tb'), 0.1, 3.0)
    # view_diagram(Testbench('tb'))
    # generate_code(Register('dut'), "VHDL", "gen/register", "register", "rtl", llm=True, generate_build_script=True, generate_purge_script=True)