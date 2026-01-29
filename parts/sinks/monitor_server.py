import socket
import json
import matplotlib.pyplot as plt
import signal
import sys
import os
from . import conf

try:
    from PyQt5.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False

# --- Constants ---
QT_QPA_PLATFORM_ENV = 'QT_QPA_PLATFORM'
WAYLAND_SESSION_TYPE = 'wayland'
XDG_SESSION_TYPE_ENV = 'XDG_SESSION_TYPE'

class MonitorServer:
    """
    A generic plotting server that visualizes data streamed via TCP.
    
    It supports different plot types configured via a dictionary.
    """
    def __init__(self, host=conf.DEFAULT_HOST, port=conf.DEFAULT_PORT, plots=None):
        """
        Args:
            host (str): Bind address.
            port (int): Bind port.
            plots (dict): Configuration for the plots.
                Format:
                {
                    'Plot Title': {
                        'type': 'time_series' | 'vector' | 'bar',
                        'signals': ['key1', 'key2', ...],
                        'ylim': (min, max)  # Optional
                    },
                    ...
                }
        """
        self.host = host
        self.port = port
        self.plots_config = plots if plots else {}
        
        # Data storage
        self.data_store = {}      # For time_series: key -> {'t': [], 'y': []}
        self.current_values = {}  # For vector/bar: key -> current_value
        
        # Initialize storage based on config
        for title, cfg in self.plots_config.items():
            for sig in cfg.get('signals', []):
                if cfg['type'] == 'time_series':
                    if sig not in self.data_store:
                        self.data_store[sig] = {'t': [], 'y': []}
                else:
                    self.current_values[sig] = 0

        self.fig = None
        self.axes = {}
        self.lines = {} # Stores plot objects (Line2D, BarContainer, etc.)
        self.running = False

    def _setup_plots(self):
        n_plots = len(self.plots_config)
        if n_plots == 0:
            print("No plots configured.")
            return

        self.fig, axs = plt.subplots(n_plots, 1, figsize=(10, 4 * n_plots))
        if n_plots == 1:
            axs = [axs]

        for ax, (title, cfg) in zip(axs, self.plots_config.items()):
            self.axes[title] = ax
            ax.set_title(title)
            ax.grid(True)
            
            if 'ylim' in cfg:
                ax.set_ylim(cfg['ylim'])

            if cfg['type'] == 'time_series':
                ax.set_xlabel('Time (s)')
                for sig in cfg['signals']:
                    line, = ax.plot([], [], label=sig)
                    self.lines[sig] = line
                ax.legend(loc='upper right')
            
            elif cfg['type'] == 'vector':
                ax.set_xlabel('Index')
                # Create a single line connecting the signal values
                indices = range(len(cfg['signals']))
                line, = ax.plot(indices, [0]*len(indices), '-o')
                self.lines[title] = line
            
            elif cfg['type'] == 'bar':
                ax.set_xlabel('Index')
                indices = range(len(cfg['signals']))
                bars = ax.bar(indices, [0]*len(indices))
                self.lines[title] = bars

        plt.tight_layout()

    def _update_plots(self):
        for title, cfg in self.plots_config.items():
            ax = self.axes[title]
            
            if cfg['type'] == 'time_series':
                updated = False
                for sig in cfg['signals']:
                    if sig in self.data_store:
                        t_data = self.data_store[sig]['t']
                        y_data = self.data_store[sig]['y']
                        self.lines[sig].set_data(t_data, y_data)
                        updated = True
                if updated and 'ylim' not in cfg:
                    ax.relim()
                    ax.autoscale_view()

            elif cfg['type'] == 'vector':
                # Construct vector from current values of signals
                values = [self.current_values.get(sig, 0) for sig in cfg['signals']]
                self.lines[title].set_ydata(values)
                if 'ylim' not in cfg:
                    ax.relim()
                    ax.autoscale_view()

            elif cfg['type'] == 'bar':
                values = [self.current_values.get(sig, 0) for sig in cfg['signals']]
                for rect, h in zip(self.lines[title], values):
                    rect.set_height(h)
                if 'ylim' not in cfg:
                    ax.relim()
                    ax.autoscale_view()

        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

    def _process_data(self, data):
        t = data.get('t', 0)
        for key, value in data.items():
            if key == 't': continue
            
            # Update current value cache
            self.current_values[key] = value
            
            # Update history for time series
            if key in self.data_store:
                self.data_store[key]['t'].append(t)
                self.data_store[key]['y'].append(value)
                # Keep buffer size manageable
                if len(self.data_store[key]['t']) > 1000:
                    self.data_store[key]['t'].pop(0)
                    self.data_store[key]['y'].pop(0)

    def start(self):
        # Ensure correct Qt platform plugin for Wayland
        if QT_QPA_PLATFORM_ENV not in os.environ and WAYLAND_SESSION_TYPE in os.environ.get(XDG_SESSION_TYPE_ENV, '').lower():
            os.environ[QT_QPA_PLATFORM_ENV] = WAYLAND_SESSION_TYPE

        app = None
        if HAS_QT:
            app = QApplication(sys.argv)

        self._setup_plots()
        if not self.fig:
            return

        plt.show(block=False)
        self.running = True
        
        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, lambda sig, frame: setattr(self, 'running', False))

        print(f"Monitor Server starting on {self.host}:{self.port}...")
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((self.host, self.port))
                s.listen()
                s.settimeout(0.1) # Non-blocking accept to allow UI updates
                
                while self.running and plt.fignum_exists(self.fig.number):
                    try:
                        conn, addr = s.accept()
                        with conn:
                            print(f"Client connected from {addr}")
                            conn.settimeout(0.01) # Non-blocking recv
                            buffer = ""
                            
                            while self.running and plt.fignum_exists(self.fig.number):
                                try:
                                    chunk = conn.recv(4096)
                                    if not chunk:
                                        break
                                    buffer += chunk.decode('utf-8')
                                    
                                    while '\n' in buffer:
                                        line, buffer = buffer.split('\n', 1)
                                        if line:
                                            try:
                                                self._process_data(json.loads(line))
                                            except json.JSONDecodeError:
                                                pass
                                    
                                    self._update_plots()
                                    if app:
                                        app.processEvents()
                                    
                                except socket.timeout:
                                    # No data, just update UI
                                    self._update_plots()
                                    if app:
                                        app.processEvents()
                                    continue
                                except Exception as e:
                                    print(f"Connection error: {e}")
                                    break
                            print("Client disconnected.")
                            
                    except socket.timeout:
                        # No connection yet, keep UI alive
                        self.fig.canvas.flush_events()
                        if app:
                            app.processEvents()
                        continue
                    except Exception as e:
                        print(f"Server error: {e}")
                        self.running = False
            except Exception as e:
                print(f"Failed to bind or start server: {e}")

        print("Monitor Server stopped.")
        plt.close('all')
