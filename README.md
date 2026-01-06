- [openformatproj/me (Modeling Environment)](#openformatprojme-modeling-environment)
  - [Introduction](#introduction)
  - [Domains](#domains)
    - [Hardware / Digital](#hardware--digital)
  - [Demos](#demos)
    - [RTL](#rtl)
      - [Register](#register)
      - [Definition](#definition)
      - [Simulation \& Waveforms](#simulation--waveforms)
      - [Visualization](#visualization)
      - [Code Generation](#code-generation)
- [License](#license)

# openformatproj/me (Modeling Environment)

This engine integrates the [`ml`](https://openformatproj.github.io/ml-docs/) framework and [`diagrams`](https://github.com/openformatproj/diagrams) tool to expose a functional environment where these two components interact seamlessly. Moreover, it defines a collection of domains and parts meant to be used to create complex and heterogeneous systems.

## Introduction

The `me` project serves as a bridge between abstract modeling, simulation, visualization, and implementation. It provides domain-specific libraries (such as digital hardware) and tools to visualize system architectures or generate target code (like VHDL) from Python-based behavioral descriptions. It also handles a more advanced configuration management and attributes propagation.

## Domains

### Hardware / Digital

The framework includes support for modeling digital logic.

-   **Logic Types**: `std_logic` equivalent (`Logic` enum with '0', '1', 'X', 'Z', etc.).
-   **Code Generation**: Automatic generation of VHDL entity and architecture from Python `Part` definitions using template-based generation and LLM integration (Gemini).
-   **Monitoring**: `@vcd_monitor` for generating Value Change Dump (VCD) files compatible with waveform viewers like GTKWave.

## Demos

These demos show how it is possible to simulate and test domain-specific parts and to generate the corresponding implementations (VHDL, Verilog/SystemVerilog, SystemC...).

### RTL

These demos deal with the RTL (Register Transfer Level) domain.

This modeling environment is usually better than domain-specific tools because:
-   **System Integration**: A domain-specific part defined with the `ml` framework can be integrated in broader and more generic systems and simulations, like for instance a [multirotor](https://github.com/openformatproj/multirotor), allowing hardware-in-the-loop style validation against physics models.
-   **Feature Richness**: The Python environment has more features than standard domain-specific testbenches, enabling seamless use of libraries for signal processing, AI, and data visualization within the simulation.
-   **Abstraction**: In `me`, a `Part` is a generic abstraction. It can represent a logic gate, a mechanical linkage, or a network packet processor. This allows for **heterogeneous simulations** that are difficult to achieve with pure domain-specific tools.

Compared to alternatives like **MyHDL**, **PyVHDL**, and **Cocotb**:
-   **Scope**: MyHDL and PyVHDL target RTL design and verification, while Cocotb focuses on verification using external simulators. `me` targets **System-Level Engineering**, allowing you to simulate a digital hardware component (like a FFT) connected directly to a physics model or a software algorithm within the same execution loop.
-   **Simulation Engine**: `me` utilizes the `ml` framework's hybrid **event-driven and synchronous dataflow** engine, supporting multi-threaded and multi-process execution strategies. This contrasts with the generator-based, single-threaded kernels typical of Python HDL simulators, enabling higher performance for complex, mixed-domain systems.

Consider, however, that a RTL `Part` corresponds and maps to a single VHDL/Verilog process. For multi-process designs, you must instantiate multiple `Part`s and wire them together manually. This aspect arises from the generalistic nature of `ml`.

#### Register

This demo (`demos/rtl/register.py`) shows how it's possible to define a RTL part using `ml`, simulate it through a testbench, generate waveforms, view the testbench diagram, and even generate the corresponding VHDL code.

#### Definition

The register is defined as a `Part` with input/output ports and a behavior method decorated to run on clock edges.

```python
class Register(Part):
    """
    A part that behaves like a simple register, updating out_0 with in_0
    whenever the clock port is updated.
    """
    def __init__(self, identifier: str):
        ports = [
            Port('clk', Port.IN, type=Logic),
            Port('rst', Port.IN, type=Logic),
            Port('in_0', Port.IN, type=Logic),
            Port('out_0', Port.OUT, type=Logic)
        ]
        super().__init__(identifier=identifier, ports=ports, scheduling_condition=all_updated, scheduling_args=('clk',))

    @rising_edge('clk')
    def behavior(self):
        if self.get_port('rst').get() == Logic.ONE:
            self.get_port('out_0').set(Logic.ZERO)
        else:
            self.get_port('out_0').set(self.get_port('in_0').get())
```

#### Simulation & Waveforms

The testbench wires a stimulus generator `Source` and a sink `Sink` to the DUT.

```python
class Source(Part):
    """
    Generates clock, reset, and input signals for the DUT.
    """
    def __init__(self, identifier: str):
        ports = [
            Port('clk', Port.OUT, type=Logic),
            Port('rst', Port.OUT, type=Logic),
            Port('in_0', Port.OUT, type=Logic),
            Port('time', Port.IN)
        ]
        super().__init__(identifier, ports=ports)
        self.cycle = 0

    def behavior(self):
        if self.get_port('time').is_updated():
            self.get_port('time').get()

        # Toggle clock
        clk_val = Logic.ONE if self.cycle % 2 == 0 else Logic.ZERO
        self.get_port('clk').set(clk_val)

        # Assert reset for the first few cycles
        if self.cycle < 5:
            self.get_port('rst').set(Logic.ONE)
        else:
            self.get_port('rst').set(Logic.ZERO)

        # Change input data periodically
        if self.cycle % 4 == 0:
            self.get_port('in_0').set(Logic.ONE)
        else:
            self.get_port('in_0').set(Logic.ZERO)

        self.trace_log(f"Cycle {self.cycle} -> Driving clk={clk_val.value}, rst={self.get_port('rst').peek().value}, in_0={self.get_port('in_0').peek().value}")
        self.cycle += 1

class Sink(Part):
    """
    Consumes the output from the DUT to prevent OverwriteError and verify behavior.
    """
    def __init__(self, identifier: str):
        ports = [Port('in_0', Port.IN, type=Logic)]
        super().__init__(identifier, ports=ports)

    def behavior(self):
        if self.get_port('in_0').is_updated():
            val = self.get_port('in_0').get()
            self.trace_log(f"Sink -> Output received = {val.value}")

@vcd_monitor('logs/waveforms.vcd', {
    'clk': 'source.clk',
    'rst': 'source.rst',
    'in_0': 'source.in_0',
    'out_0': 'dut.out_0'
}, time_path='sync.timer_out')
class Testbench(Part):

    def __init__(self, identifier: str):

        event_queues = [EventQueue('timer_q', EventQueue.IN, size=1)]
        
        parts = {
            'sync': EventToDataSynchronizer('sync', 'timer_in', 'timer_out', float),
            'source': Source('source'),
            'dut': Register('dut'),
            'sink': Sink('sink')
        }
        
        super().__init__(identifier, parts=parts, event_queues=event_queues, execution_strategy=Execution.sequential())
        
        # Wire the Timer event to the Synchronizer
        self.wire_event('timer_q', 'sync.timer_in')
        
        # Wire Synchronizer time to Source
        self.wire('sync.timer_out', 'source.time')
        
        # Wire Source signals to DUT
        self.wire('source.clk', 'dut.clk')
        self.wire('source.rst', 'dut.rst')
        self.wire('source.in_0', 'dut.in_0')
        
        # Wire DUT output to Sink
        self.wire('dut.out_0', 'sink.in_0')
```

Thanks to `@vcd_monitor` it's possible to probe signals and create a VCD file to show their waveforms.

<p id="figure-1"/>

![Figure 1: Waveforms viewed in a VCD viewer](img/1.png)
<p align="center">Figure 1: Waveforms viewed in a VCD viewer</p>

The simulation is performed by running `simulate()`. <a href="#figure-1">Figure 1</a> shows the outcome of the VCD monitor, if enabled.

#### Visualization

The structure of the testbench can be serialized and visualized using the `diagrams` integration. <a href="#figure-2">Figure 2</a> shows the outcome of executing `view_testbench_diagram()`.

<p id="figure-2"/>

![Figure 2: Testbench structure visualization](img/2.png)
<p align="center">Figure 2: Testbench structure visualization</p>

#### Code Generation

The framework can generate VHDL code by combining Jinja2 templates for the entity definition and LLM calls (e.g., Google Gemini) to translate the Python behavior into VHDL architecture.

```python
vhdl_code = generate_code(
    Register('dut'), 
    language="VHDL", 
    entity_name="register", 
    architecture_name="rtl", 
    llm_client=gemini_client
)
```

Running `generate_vhdl_code(llm=False)` produces the following outcome:

```vhdl
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity register is
    Port (
           clk : in STD_LOGIC;
           rst : in STD_LOGIC;
           in_0 : in STD_LOGIC;
           out_0 : out STD_LOGIC
    );
end register;

architecture rtl of register is
begin

    -- TODO: Implement behavior. Reference Python code:
    --     @rising_edge('clk')
    --     def behavior(self):
    --         if self.get_port('rst').get() == Logic.ONE:
    --             self.get_port('out_0').set(Logic.ZERO)
    --         else:
    --             self.get_port('out_0').set(self.get_port('in_0').get())

end rtl;
```

While running `generate_vhdl_code(llm=True)` produces a complete code:

```vhdl
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity register is
    Port (
           clk : in STD_LOGIC;
           rst : in STD_LOGIC;
           in_0 : in STD_LOGIC;
           out_0 : out STD_LOGIC
    );
end register;

architecture rtl of register is
begin

    -- Generated by gemini-2.5-flash-lite
    process(clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                out_0 <= '0';
            else
                out_0 <= in_0;
            end if;
        end if;
    end process;

end rtl;
```

# License

![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)

This project is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). You are free to use, modify, and distribute this software, provided that you include proper attribution to the original author(s). Redistribution must retain the original copyright notice and this license.