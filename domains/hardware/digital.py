from enum import Enum
from typing import Optional, Callable
import inspect
import os
from functools import wraps
from ml.engine import Part, Port
from jinja2 import Template

class Logic(Enum):
    """A type for HDL standard logic."""
    U = 'U'  # Uninitialized
    X = 'X'  # Forcing Unknown
    ZERO = '0'  # Forcing 0
    ONE = '1'  # Forcing 1
    Z = 'Z'  # High Impedance
    W = 'W'  # Weak Unknown
    L = 'L'  # Weak 0
    H = 'H'  # Weak 1
    DONT_CARE = '-'  # Don't care

    def __invert__(self):
        if self == Logic.ZERO:
            return Logic.ONE
        if self == Logic.ONE:
            return Logic.ZERO
        if self == Logic.L:
            return Logic.H
        if self == Logic.H:
            return Logic.L
        return Logic.X

def rising_edge(port_name):
    """
    Decorator to execute the behavior only on a rising edge of the specified port.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            port = self.get_port(port_name)
            current_val = port.peek()
            prev_attr = f"_prev_{port_name}"
            prev_val = getattr(self, prev_attr, Logic.U)
            setattr(self, prev_attr, current_val)
            
            if (prev_val in [Logic.ZERO, Logic.L]) and (current_val in [Logic.ONE, Logic.H]):
                return func(self, *args, **kwargs)
        return wrapper
    return decorator

def generate_code(part: Part, language: str = "VHDL", entity_name: Optional[str] = None, architecture_name: str = "rtl", llm_client: Optional[Callable[[str], str]] = None) -> str:
    """
    Generates HDL code for a given Part.

    Args:
        part: The Part instance to generate code for.
        language: The target language (default: "VHDL").
        entity_name: The name of the entity/module. If None, defaults to the part's class name in lowercase.
        architecture_name: The name of the architecture (default: "rtl").
        llm_client: An optional function that accepts a prompt string and returns the generated architecture.

    Returns:
        str: The generated HDL code.

    Raises:
        ValueError: If the language is not supported.
        Exception: If the `llm_client` raises an error.
    """
    if language.upper() != "VHDL":
        raise ValueError(f"Unsupported language: {language}")

    if entity_name is None:
        entity_name = type(part).__name__.lower()
    
    ports = []
    for p in part.get_ports(Port.IN) + part.get_ports(Port.OUT):
        ports.append({
            "name": p.get_identifier(),
            "direction": "in" if p.get_direction() == Port.IN else "out",
            "type": "STD_LOGIC"
        })

    base_path = os.path.dirname(__file__)
    with open(os.path.join(base_path, 'VHDL', 'entity.vhd'), 'r') as f:
        entity_template_content = f.read()
    entity_template = Template(entity_template_content)
    
    entity_str = entity_template.render(entity_name=entity_name, ports=ports)
    
    if llm_client:
        try:
            behavior_code = inspect.getsource(part.behavior)
        except Exception:
            behavior_code = "-- Could not retrieve source code."
            
        with open(os.path.join(base_path, 'VHDL', 'generation_prompt.txt'), 'r') as f:
            prompt_template_content = f.read()
        prompt_template = Template(prompt_template_content)
        prompt = prompt_template.render(
            behavior_code=behavior_code
        )
        generated_behavior = llm_client(prompt)
        indented_behavior = "\n".join(["    " + line for line in generated_behavior.splitlines()])
        architecture_body = (
            f"\narchitecture {architecture_name} of {entity_name} is\n"
            f"begin\n\n"
            f"{indented_behavior}\n\n"
            f"end {architecture_name};"
        )
    else:
        try:
            behavior_code = inspect.getsource(part.behavior)
            behavior_lines = behavior_code.splitlines()
        except Exception:
            behavior_lines = []

        with open(os.path.join(base_path, 'VHDL', 'architecture.vhd'), 'r') as f:
            arch_template_content = f.read()
        arch_template = Template(arch_template_content)
        architecture_body = arch_template.render(
            architecture_name=architecture_name,
            entity_name=entity_name,
            behavior_lines=behavior_lines
        )
    
    return entity_str + "\n" + architecture_body