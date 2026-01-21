You are an expert VHDL hardware designer. Your task is to translate the following Python behavioral code into a synthesizable VHDL process.

{{ entity_context }}

**CRITICAL RULES - READ CAREFULLY**:
1. **NO DYNAMIC ARRAYS**: The ports listed in "Entity Context" are SCALAR signals (e.g., `x0`, `x1`). They are NOT arrays. You CANNOT access them as `x(i)`.
2. **UNROLL LOOPS**: You MUST unroll all Python loops that iterate over port indices.
   - Python: `for i in range(2): write(f'y{i}', 0)`
   - VHDL: `y0 <= 0; y1 <= 0;`
   - **WRONG**: `for i in 0 to 1 loop y(i) <= 0; end loop;` (This will fail synthesis because `y` is not an array).
3. **STRICT TYPES**:
   - If a port is defined as `INTEGER`, assign integer literals or variables directly.
   - **DO NOT** cast `INTEGER` to `std_logic_vector` or `unsigned`.
   - **DO NOT** use attributes like `'length` on integers.
   - Map `Logic.ONE` to `'1'`, `Logic.ZERO` to `'0'`, and `Logic.Z` to `'Z'`.
4. **NO REAL SIGNALS / PRE-CALCULATION ALLOWED**:
   - **SIGNALS/VARIABLES**: Do NOT use `real` types for synthesizable signals or variables.
   - **CONSTANTS**: You MAY use `real` constants and operations ONLY to pre-calculate integer coefficients (e.g. twiddle factors).
   - **Strategy**: Define a `real` scaling constant (e.g. `SCALE : real := 32768.0;`). Calculate coefficients using `round(val * SCALE)`. Cast the final constant to `integer`.
   - Example: `constant C : integer := integer(round(cos(MATH_PI/4.0) * 32768.0));`
   - Pre-calculate the integer constants based on the loop index.
   - **DECLARE EVERYTHING**: You MUST declare all constants (e.g., `W_R_SCALED`) before using them.
   - **NO RECORDS**: Do NOT define `record` types inside the process. Use simple `array` of `integer` or scalar constants.
   - **MATH CONSTANTS**: Use `MATH_PI` from `IEEE.MATH_REAL` instead of `atan2` or `arctan`. Ensure you cast integers to real (e.g., `real(N)`) when dividing in constant calculations.
5. **VARIABLES vs SIGNALS**:
   - Use `variable` for local state or intermediate calculations within the process.
   - Map Python instance attributes (e.g., `self.cnt`) to VHDL variables declared **inside** the process (before `begin`).
   - **MINIMIZE VARIABLES**: Use variables for intermediate values only if strictly needed (e.g. to preserve read-after-write semantics). Do not introduce variables for direct assignments to outputs.
   - **SYNTAX**: Variable assignment uses `:=` (e.g., `v := 10;`). Signal assignment uses `<=` (e.g., `s <= 10;`).
   - **OUTPUTS**: Assign directly to output ports using `<=` (e.g., `y_r_0 <= result;`). Do not buffer outputs in variables unless necessary.
6. **LATCH PREVENTION**: Ensure that all signals are assigned a value in every branch of conditional statements to avoid inferring latches, unless a latch is explicitly intended with the comment `# @latch`.
7. **ASSIGNMENT TARGETS**: The left-hand side of a signal assignment (`<=`) MUST be a specific port name (e.g., `y_r_2`).
   - It CANNOT be an expression (e.g., `y_r_0 + 2 <= ...` is INVALID).
   - You MUST resolve Python f-strings like `f'y_r_{k+half_n}'` to the actual port name (e.g., `y_r_2`) based on the current loop index and configuration values.
   - **CLOCK EDGE**: If the Python code uses `@rising_edge('clk')`, you MUST wrap the logic in `if rising_edge(clk) then ... end if;`.
   - **NO UNDEFINED FUNCTIONS**: Do NOT use functions like `tostore` or `to_integer` unless they are standard.
8. **CONSTANT EVALUATION**: Python variables derived from configuration (like `half_n = n // 2`) MUST be evaluated to integer literals in VHDL. Do NOT declare VHDL variables for them.
9. **STRUCTURE**: The output must be a single VHDL `process` block. Do not generate `entity` or `architecture` wrappers.

Common Mistakes (DO NOT DO THIS):
- **WRONG**: `y_r_0 + 2 <= val;` (Syntax Error: Arithmetic on LHS)
- **RIGHT**: `y_r_2 <= val;` (Correct: Port name resolved)
- **WRONG**: `variable half_n : integer := 2;` (Do not use variables for constants)
- **RIGHT**: Use literal `2` directly in calculations or indices.
- **WRONG**: `variable t : real;` (Do not use real types)
- **RIGHT**: `variable t : integer;` (Use scaled integers)
- **WRONG**: `variable v : integer; ... v <= 10;` (Wrong assignment operator for variable)
- **RIGHT**: `variable v : integer; ... v := 10;` (Correct assignment operator for variable)

Failure Conditions:
- Use of scalar variables that are neither finite values (`Logic`, `bool`, `Enum`...) nor numeric types (`int`, `float`...).
- Use of data structures (e.g., lists, dictionaries) that dynamically change size at runtime.
- Use of file I/O operations or system calls.
- Use of recursive function calls.
- Use of infinite loops or loops with bounds not determinable at compile time.
In these cases, the generation must fail.

Example 1 (Standard Logic):
Python:
    @rising_edge('clk')
    def behavior(self):
        if self.read('rst') == Logic.ONE:
            self.write('q', Logic.ZERO)
        else:
            self.write('q', self.read('d'))
VHDL:
    process(clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                q <= '0';
            else
                q <= d;
            end if;
        end if;
    end process;

Example 2 (Internal State):
Python:
    self.internal_state = Logic.ZERO
    @rising_edge('clk')
    def behavior(self):
        if self.read('rst') == Logic.ONE:
            self.internal_state = Logic.ZERO
        else:
            self.internal_state = self.read('d')
        self.write('q', self.internal_state)
VHDL:
    process(clk)
        variable internal_state : std_logic := '0';
    begin
        if rising_edge(clk) then
            if rst = '1' then
                internal_state := '0';
            else
                internal_state := d;
            end if;
            q <= internal_state;
        end if;
    end process;

Example 3 (Loop Unrolling & Integers):
Entity Context:
- **Ports**:
  - y0: out INTEGER
  - y1: out INTEGER
- **Configuration**:
  - n = 2
Python:
    self.n = 2
    for i in range(self.n):
        self.write(f'y{i}', 0)
VHDL:
    y0 <= 0;
    y1 <= 0;

Example 4 (Calculated Indices):
Entity Context:
- **Ports**:
  - y0: out INTEGER
  - y2: out INTEGER
- **Configuration**:
  - offset = 2
Python:
    self.offset = 2
    for i in range(1):
        self.write(f'y{i}', 10)
        self.write(f'y{i+self.offset}', 20)
VHDL:
    y0 <= 10;
    y2 <= 20;

Python Behavior:
{{ behavior_code }}

Generate the VHDL `process` block now.
