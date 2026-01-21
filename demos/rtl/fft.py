from ml.engine import Part, Port, EventQueue
from ml.strategies import Execution
from ml.strategies import all_updated
from me.domains.hardware.digital import Logic, rising_edge, generate_code
from me.parts.hardware.digital import Clock, vcd_monitor
from me.services import view_diagram, simulate
import cmath

N_POINTS = 8

class FFT_Leaf(Part):
    """
    The base case for the recursive FFT (N=1).
    It simply passes the input to the output when started.
    """
    def __init__(self, identifier: str):
        ports = [
            Port('clk', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('rst', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('start', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('done', Port.OUT, type=Logic, init_value=Logic.ZERO, semantic=Port.PERSISTENT),
            Port('x0', Port.IN, type=int, init_value=0, semantic=Port.PERSISTENT),
            Port('y0_r', Port.OUT, type=int, init_value=0, semantic=Port.PERSISTENT),
            Port('y0_i', Port.OUT, type=int, init_value=0, semantic=Port.PERSISTENT)
        ]
        super().__init__(identifier, ports=ports, scheduling_condition=all_updated, scheduling_args=('clk',))

    @rising_edge('clk')
    def behavior(self):
        if self.read('rst') == Logic.ONE:
            self.write('done', Logic.ZERO)
            self.write('y0_r', 0)
            self.write('y0_i', 0)
        elif self.read('start') == Logic.ONE:
            self.write('y0_r', self.read('x0'))
            self.write('y0_i', 0)
            self.write('done', Logic.ONE)
        else:
            self.write('done', Logic.ZERO)

class FFT_Combiner(Part):
    """
    Performs the butterfly operations to combine results from Even and Odd sub-FFTs.
    """
    def __init__(self, identifier: str, n: int):
        self.n = n
        ports = [
            Port('clk', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('rst', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('done_even', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('done_odd', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('done', Port.OUT, type=Logic, init_value=Logic.ZERO, semantic=Port.PERSISTENT),
        ]
        # Inputs from Even/Odd sub-FFTs
        half_n = n // 2
        for i in range(half_n):
            ports.append(Port(f'e_r_{i}', Port.IN, type=int, init_value=0, semantic=Port.PERSISTENT))
            ports.append(Port(f'e_i_{i}', Port.IN, type=int, init_value=0, semantic=Port.PERSISTENT))
            ports.append(Port(f'o_r_{i}', Port.IN, type=int, init_value=0, semantic=Port.PERSISTENT))
            ports.append(Port(f'o_i_{i}', Port.IN, type=int, init_value=0, semantic=Port.PERSISTENT))
        # Outputs
        for i in range(n):
            ports.append(Port(f'y_r_{i}', Port.OUT, type=int, init_value=0, semantic=Port.PERSISTENT))
            ports.append(Port(f'y_i_{i}', Port.OUT, type=int, init_value=0, semantic=Port.PERSISTENT))
        
        super().__init__(identifier, ports=ports, scheduling_condition=all_updated, scheduling_args=('clk',))

    @rising_edge('clk')
    def behavior(self):
        if self.read('rst') == Logic.ONE:
            self.write('done', Logic.ZERO)
            for i in range(self.n):
                self.write(f'y_r_{i}', 0)
                self.write(f'y_i_{i}', 0)
        elif self.read('done_even') == Logic.ONE and self.read('done_odd') == Logic.ONE:
            half_n = self.n // 2
            for k in range(half_n):
                e_r = self.read(f'e_r_{k}')
                e_i = self.read(f'e_i_{k}')
                o_r = self.read(f'o_r_{k}')
                o_i = self.read(f'o_i_{k}')
                
                # Twiddle factor W_N^k
                w = cmath.exp(-2j * cmath.pi * k / self.n)
                
                # T = w * odd
                t_r = w.real * o_r - w.imag * o_i
                t_i = w.real * o_i + w.imag * o_r
                
                # Y[k] = E[k] + T
                self.write(f'y_r_{k}', int(e_r + t_r))
                self.write(f'y_i_{k}', int(e_i + t_i))
                
                # Y[k + N/2] = E[k] - T
                self.write(f'y_r_{k+half_n}', int(e_r - t_r))
                self.write(f'y_i_{k+half_n}', int(e_i - t_i))
            
            self.write('done', Logic.ONE)
        else:
            self.write('done', Logic.ZERO)

class FFT(Part):
    """
    A generic structural FFT implementation using the Cooley-Tukey algorithm.
    Inputs are `n` real samples (integers).
    Outputs are `n` complex samples (real and imag parts, integers).
    """
    def __init__(self, identifier: str, n: int):
        if n < 1 or (n & (n - 1) != 0):
            raise ValueError(f"n must be a power of 2, got {n}")
        self.n = n
        ports = [
            Port('clk', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('rst', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('start', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('done', Port.OUT, type=Logic, init_value=Logic.ZERO, semantic=Port.PERSISTENT)
        ]
        # Dynamic ports based on n
        for i in range(n):
            ports.append(Port(f'x{i}', Port.IN, type=int, init_value=0, semantic=Port.PERSISTENT))
            ports.append(Port(f'y{i}_r', Port.OUT, type=int, init_value=0, semantic=Port.PERSISTENT))
            ports.append(Port(f'y{i}_i', Port.OUT, type=int, init_value=0, semantic=Port.PERSISTENT))

        # Define subparts
        parts = {}
        if n == 1:
            parts['leaf'] = FFT_Leaf('leaf')
        else:
            parts['even'] = FFT('even', n // 2)
            parts['odd'] = FFT('odd', n // 2)
            parts['comb'] = FFT_Combiner('comb', n)

        super().__init__(identifier=identifier, ports=ports, parts=parts, execution_strategy=Execution.sequential())

        # Wiring
        if n == 1:
            self.wire('clk', 'leaf.clk')
            self.wire('rst', 'leaf.rst')
            self.wire('start', 'leaf.start')
            self.wire('leaf.done', 'done')
            self.wire('x0', 'leaf.x0')
            self.wire('leaf.y0_r', 'y0_r')
            self.wire('leaf.y0_i', 'y0_i')
        else:
            # Control signals
            self.wire('clk', 'even.clk')
            self.wire('clk', 'odd.clk')
            self.wire('clk', 'comb.clk')
            self.wire('rst', 'even.rst')
            self.wire('rst', 'odd.rst')
            self.wire('rst', 'comb.rst')
            
            self.wire('start', 'even.start')
            self.wire('start', 'odd.start')
            
            self.wire('even.done', 'comb.done_even')
            self.wire('odd.done', 'comb.done_odd')
            self.wire('comb.done', 'done')
            
            # Data inputs (split even/odd)
            for k in range(n // 2):
                self.wire(f'x{2*k}', f'even.x{k}')
                self.wire(f'x{2*k+1}', f'odd.x{k}')
            
            # Data outputs from sub-FFTs to Combiner
            for k in range(n // 2):
                self.wire(f'even.y{k}_r', f'comb.e_r_{k}')
                self.wire(f'even.y{k}_i', f'comb.e_i_{k}')
                self.wire(f'odd.y{k}_r', f'comb.o_r_{k}')
                self.wire(f'odd.y{k}_i', f'comb.o_i_{k}')
            
            # Data outputs from Combiner to FFT outputs
            for k in range(n):
                self.wire(f'comb.y_r_{k}', f'y{k}_r')
                self.wire(f'comb.y_i_{k}', f'y{k}_i')

    # @rising_edge('clk')
    # def behavior(self):
    #     if self.read('rst') == Logic.ONE:
    #         self.write('done', Logic.ZERO)
    #         for i in range(self.n):
    #             self.write(f'y{i}_r', 0)
    #             self.write(f'y{i}_i', 0)
    #     else:
    #         if self.read('start') == Logic.ONE:
    #             # Read inputs
    #             x = []
    #             for i in range(self.n):
    #                 x.append(self.read(f'x{i}'))
                
    #             # Generic Recursive FFT (Cooley-Tukey)
    #             def fft_recursive(seq):
    #                 n = len(seq)
    #                 if n <= 1: return seq
    #                 even = fft_recursive(seq[0::2])
    #                 odd =  fft_recursive(seq[1::2])
    #                 T = [cmath.exp(-2j * cmath.pi * k / n) * odd[k] for k in range(n // 2)]
    #                 return [even[k] + T[k] for k in range(n // 2)] + \
    #                        [even[k] - T[k] for k in range(n // 2)]
                
    #             y = fft_recursive(x)

    #             # Write outputs
    #             for i in range(self.n):
    #                 self.write(f'y{i}_r', int(y[i].real))
    #                 self.write(f'y{i}_i', int(y[i].imag))
                
    #             self.write('done', Logic.ONE)
    #         else:
    #             self.write('done', Logic.ZERO)

class Source(Part):
    """
    Generates reset and input signals for the DUT.
    """
    def __init__(self, identifier: str, n: int):
        self.n = n
        ports = [
            Port('clk', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('rst', Port.OUT, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('start', Port.OUT, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
        ]
        for i in range(n):
            ports.append(Port(f'x{i}', Port.OUT, type=int, init_value=0, semantic=Port.PERSISTENT))
        super().__init__(identifier, ports=ports, scheduling_condition=all_updated, scheduling_args=('clk',))
        self.cycle = 0

    @rising_edge('clk')
    def behavior(self):
        # Assert reset for the first few cycles
        if self.cycle < 2:
            self.write('rst', Logic.ONE)
            self.write('start', Logic.ZERO)
        else:
            self.write('rst', Logic.ZERO)
            # Pulse start every 10 cycles
            if (self.cycle - 2) % 10 == 0:
                self.write('start', Logic.ONE)
                # DC component test: all 1s
                for i in range(self.n):
                    self.write(f'x{i}', 1)
            elif (self.cycle - 2) % 10 == 5:
                 # Nyquist test: 1, -1, 1, -1...
                self.write('start', Logic.ONE)
                for i in range(self.n):
                    self.write(f'x{i}', 1 if i % 2 == 0 else -1)
            else:
                self.write('start', Logic.ZERO)
        
        self.cycle += 1

class Sink(Part):
    """
    Consumes the output from the DUT to prevent OverwriteError and verify behavior.
    """
    def __init__(self, identifier: str, n: int):
        self.n = n
        ports = [
            Port('done', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
        ]
        for i in range(n):
            ports.append(Port(f'y{i}_r', Port.IN, type=int, init_value=0, semantic=Port.PERSISTENT))
            ports.append(Port(f'y{i}_i', Port.IN, type=int, init_value=0, semantic=Port.PERSISTENT))
        super().__init__(identifier, ports=ports)

    def behavior(self):
        if self.read('done') == Logic.ONE:
            res = []
            for i in range(self.n):
                yr = self.read(f'y{i}_r')
                yi = self.read(f'y{i}_i')
                res.append(f"Y{i}=({yr}, {yi}j)")
            self.trace_log(f"Sink -> FFT Done. {', '.join(res)}")

monitor_signals = {
    'clock.clk': 'clock.clk',
    'source.start': 'source.start',
    'dut.done': 'dut.done',
}
for i in range(N_POINTS):
    monitor_signals[f'source.x{i}'] = (f'source.x{i}', 16)
    monitor_signals[f'dut.y{i}_r'] = (f'dut.y{i}_r', 16)
    monitor_signals[f'dut.y{i}_i'] = (f'dut.y{i}_i', 16)

@vcd_monitor('logs/waveforms.vcd', monitor_signals, time_path='clock.time_port')
class Testbench(Part):

    def __init__(self, identifier: str):
        event_queues = [EventQueue('timer_q', EventQueue.IN, size=1)]
        
        parts = {
            'clock': Clock('clock'),
            'source': Source('source', n=N_POINTS),
            'dut': FFT('dut', n=N_POINTS),
            'sink': Sink('sink', n=N_POINTS)
        }
        
        super().__init__(identifier, parts=parts, event_queues=event_queues, execution_strategy=Execution.sequential())
        
        # Wire the Timer event to the Clock
        self.wire_event('timer_q', 'clock.time')
        
        # Wire Clock to Source and DUT
        self.wire('clock.clk', 'source.clk')
        self.wire('clock.clk', 'dut.clk')
        
        # Wire Source signals to DUT
        self.wire('source.rst', 'dut.rst')
        self.wire('source.start', 'dut.start')
        
        for i in range(N_POINTS):
            self.wire(f'source.x{i}', f'dut.x{i}')
            self.wire(f'dut.y{i}_r', f'sink.y{i}_r')
            self.wire(f'dut.y{i}_i', f'sink.y{i}_i')
        
        # Wire DUT output to Sink
        self.wire('dut.done', 'sink.done')

if __name__ == "__main__":
    def trace_filter(record):
        return record.event in ['TRANSFER', 'SET_PAYLOAD']

    simulate(Testbench('tb'), 0.1, 3.0, trace_filter)
    # view_diagram(Testbench('tb'))
    # generate_code(FFT('dut', n=N_POINTS), "VHDL", "gen/fft", "fft", "structural", llm=True, generate_build_script=True, generate_purge_script=True)