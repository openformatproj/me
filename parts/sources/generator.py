from typing import Callable, Any
from ml.engine import Part, Port, EventQueue

class Generator(Part):
    """
    A generic generator that drives its output based on a function of time.
    """
    def __init__(self, identifier: str, func: Callable[[float], Any], port_type: type = float, use_data_port: bool = False):
        self.use_data_port = use_data_port
        ports = [
            Port('out', Port.OUT, type=port_type, semantic=Port.PERSISTENT)
        ]
        event_queues = []
        if use_data_port:
            ports.append(Port('time_in', Port.IN, type=float))
        else:
            event_queues.append(EventQueue('time', EventQueue.IN, size=1))
            
        super().__init__(identifier=identifier, ports=ports, event_queues=event_queues)
        self.func = func

    def behavior(self):
        if self.use_data_port:
            t = self.read('time_in')
        else:
            event_queue = self.get_event_queue('time')
            if event_queue.is_empty():
                return
            t = event_queue.pop()

        val = self.func(t)
        self.write('out', val)
        self.trace_log(f"Generator@time {t} -> Drive out {val}")