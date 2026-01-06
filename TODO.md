# TODO

- [ ] **Diagram Editor Integration**: Implement a way to define a system through the diagram view. This means that built-in parts can be imported, connected together graphically, and then the Python codebase can be generated from the diagram.
- [ ] **Multi-Language Generation**: Extend `generate_code` to support Verilog and SystemVerilog.
- [ ] **New Domains**: Add support for continuous control systems (transfer functions, state-space) and physical modeling.
- [ ] **Enhanced LLM Prompts**: Improve prompt engineering for more complex behavioral translation (e.g., state machines).
- [ ] **Unit Testing**: Add comprehensive unit tests for the digital domain parts and generation logic.
- [ ] **Configuration Management**: Implement advanced configuration management and attribute propagation mechanisms.
    - *Example*: Propagate port type when a typed port is connected to a port without type, directly or indirectly.
- [ ] **Standard Library**: Implement a set of standard digital parts (Mux, Demux, ALU, RAM, ROM).
- [ ] **Bus Abstractions**: Create `Interface` subclasses for standard buses (e.g., AXI-Stream, Wishbone) to bundle signals.
- [ ] **Waveform Viewer**: Add a utility to automatically launch GTKWave with the generated VCD file.