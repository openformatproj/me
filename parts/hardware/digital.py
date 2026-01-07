from ml.engine import Part, Port
from ml.strategies import all_updated
from me.domains.hardware.digital import Logic
from functools import wraps
import datetime

class VCDMonitor(Part):
    """
    A monitor part that logs signal changes to a VCD (Value Change Dump) file.
    """
    def __init__(self, identifier: str, filename: str, time_port: str, signals: dict):
        """
        Initializes the VCD Monitor.

        Args:
            identifier: The unique name for this part.
            filename: The path to the output VCD file.
            time_port: The name of the port receiving the simulation time.
            signals: A dictionary mapping input port names to VCD signal names.
                     Example: {'clk': 'clock', 'in_0': 'data_in'}
        """
        self.filename = filename
        self.time_port_name = time_port
        self.signals = signals
        self.signal_vars = {} # port_name -> vcd_id
        
        # Create ports: one for time, and one for each signal to monitor
        ports = [Port(time_port, Port.IN)]
        for port_name in signals.keys():
            ports.append(Port(port_name, Port.IN))
            
        # Schedule this part whenever any port is updated
        super().__init__(identifier, ports=ports)
        
        self.file = open(filename, 'w')
        self.last_timestamp = -1
        self.write_header()

    def write_header(self):
        date = datetime.datetime.now().strftime("%b %d %Y %H:%M:%S")
        self.file.write(f"$date\n   {date}\n$end\n")
        self.file.write("$version\n   ML Framework VCD Monitor\n$end\n")
        self.file.write("$timescale 1ms $end\n") # Assuming ms for simplicity
        self.file.write("$scope module top $end\n")
        
        for i, (port_name, var_name) in enumerate(self.signals.items()):
            vcd_id = f"v{i}"
            self.signal_vars[port_name] = vcd_id
            self.file.write(f"$var wire 1 {vcd_id} {var_name} $end\n")
            
        self.file.write("$upscope $end\n")
        self.file.write("$enddefinitions $end\n")
        self.file.write("$dumpvars\n")
        self.file.write("$end\n")

    def behavior(self):
        t_port = self.get_port(self.time_port_name)
        if t_port.is_updated():
            time_val = t_port.get()
        else:
            time_val = t_port.peek()

        if time_val is not None:
            timestamp = int(time_val * 1000) # Convert seconds to ms
            if timestamp > self.last_timestamp:
                self.file.write(f"#{timestamp}\n")
                self.last_timestamp = timestamp

            for port_name, vcd_id in self.signal_vars.items():
                port = self.get_port(port_name)
                if port.is_updated():
                    val = port.get()
                    # Map Logic values to VCD values (0, 1, x, z)
                    vcd_val = '1' if val in [Logic.ONE, Logic.H] else \
                              '0' if val in [Logic.ZERO, Logic.L] else \
                              'z' if val == Logic.Z else 'x'
                    self.file.write(f"{vcd_val}{vcd_id}\n")

    def term(self):
        if self.file:
            self.file.close()
        super().term()

def vcd_monitor(filename: str, signals: dict, time_path: str = 'time'):
    """
    Class decorator to attach a VCDMonitor to a Part.
    
    Args:
        filename: VCD output filename.
        signals: Dict mapping VCD signal names to paths in the part (e.g. {'clk': 'source.clk'}).
        time_path: Path to the time signal (e.g. 'sync.timer_out').
    """
    def decorator(cls):
        original_init = cls.__init__
        
        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            
            monitor_signals = {k: k for k in signals.keys()}
            monitor = VCDMonitor('vcd', filename, 'time', monitor_signals)
            self.add_part(monitor)
            
            def resolve_port(path):
                if '.' in path:
                    part_id, port_id = path.split('.', 1)
                    return self.get_part(part_id).get_port(port_id)
                return self.get_port(path)
            
            self.connect(resolve_port(time_path), monitor.get_port('time'))
            
            for vcd_name, path in signals.items():
                self.connect(resolve_port(path), monitor.get_port(vcd_name))
                
        cls.__init__ = new_init
        return cls
    return decorator