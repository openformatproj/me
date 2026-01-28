from ml.engine import Part, Port
from me.domains.hardware.digital import Logic, rising_edge
from ml.strategies import all_updated

class ADC(Part):
    """
    Analog to Digital Converter.
    Converts a float input to an integer output on the rising edge of the clock.
    """
    def __init__(self, identifier: str, bits: int = 16, v_ref: float = 1.0):
        ports = [
            Port('clk', Port.IN, type=Logic, init_value=Logic.U, semantic=Port.PERSISTENT),
            Port('in_analog', Port.IN, type=float, init_value=0.0, semantic=Port.PERSISTENT),
            Port('out_digital', Port.OUT, type=int, init_value=0, semantic=Port.PERSISTENT)
        ]
        super().__init__(identifier, ports=ports, scheduling_condition=all_updated, scheduling_args=('clk',))
        self.v_ref = v_ref
        self.scale = (1 << (bits - 1)) - 1

    @rising_edge('clk')
    def behavior(self):
        val = self.read('in_analog')
        # Scale and clamp to integer range
        res = max(-self.scale, min(self.scale, int((val / self.v_ref) * self.scale)))
        self.write('out_digital', res)