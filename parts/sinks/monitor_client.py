import socket
import json
from ml.engine import Part, Port
from ml.strategies import time_updated
from ml.tracer import Tracer
from ml.enums import LogLevel
from . import conf

class Monitor(Part):
    """
    A generic behavioral part that acts as a client to a remote plotting server.

    It collects data from its input ports and streams it as JSON objects
    over a TCP socket.
    """
    def __init__(self, identifier: str, signals: dict, host: str = conf.DEFAULT_HOST, port: int = conf.DEFAULT_PORT, time_port: str = 'time', decimation: int = 1):
        """
        Initializes the Monitor client.

        Args:
            identifier (str): The unique name for this part.
            signals (dict or list): A mapping of input port names to JSON keys.
                                    If a list is provided, keys will match port names.
                                    Example: {'dut.y0': 'y0'} or ['x0', 'x1']
            host (str): The hostname of the plot server. Defaults to conf.DEFAULT_HOST.
            port (int): The port of the plot server. Defaults to conf.DEFAULT_PORT.
            time_port (str): The name of the port carrying simulation time.
            decimation (int): Send data only every Nth tick.
        """
        # Normalize signals to a dict
        self.signal_map = {}
        if isinstance(signals, list):
            for s in signals:
                self.signal_map[s] = s
        else:
            self.signal_map = signals

        # Create ports
        ports = [Port(time_port, Port.IN)]
        for port_name in self.signal_map.keys():
            ports.append(Port(port_name, Port.IN))

        super().__init__(identifier, ports=ports, scheduling_condition=time_updated)

        self.host = host
        self.port = port
        self.time_port_name = time_port
        self.socket = None
        self.decimation = decimation
        self.tick_counter = 0

        self.add_hook('init', self._connect)
        self.add_hook('term', self._disconnect)

    def _connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            Tracer.log(LogLevel.INFO, self.get_identifier(), "CONNECTED", {"host": self.host, "port": self.port})
        except ConnectionRefusedError:
            Tracer.log(LogLevel.ERROR, self.get_identifier(), "CONNECT_FAIL", {"message": "Is the monitor_server running?"})
            self.socket = None

    def _disconnect(self):
        if self.socket:
            self.socket.close()
            Tracer.log(LogLevel.INFO, self.get_identifier(), "DISCONNECTED", {})

    def behavior(self):
        if not self.socket:
            return

        self.tick_counter += 1
        if self.tick_counter % self.decimation != 0:
            return

        # Collect data
        data = {}
        
        # Read time
        t_port = self.get_port(self.time_port_name)
        if t_port.is_updated():
            data['t'] = float(t_port.get())
        else:
            # Fallback if time is persistent and not updated this cycle (unlikely with all_updated)
            data['t'] = float(t_port.peek())

        # Read signals
        for port_name, json_key in self.signal_map.items():
            port = self.get_port(port_name)
            if port.is_updated():
                val = port.get()
            else:
                val = port.peek()
            
            if val is None:
                val = 0
            # Ensure basic types for JSON serialization
            if hasattr(val, 'item'): # numpy types
                val = val.item()
            data[json_key] = val

        # Send data
        try:
            message = json.dumps(data) + '\n'
            self.socket.sendall(message.encode('utf-8'))
        except (BrokenPipeError, ConnectionResetError, OSError):
            Tracer.log(LogLevel.WARNING, self.get_identifier(), "SEND_FAIL", {"message": "Connection lost"})
            self.socket = None
