from enum import Enum
from typing import Optional, Callable, Tuple, Dict
import inspect
import os
from functools import wraps
from ml.engine import Part, Port
from jinja2 import Template
import json
import hashlib
from .conf import VHDL_RESERVED_WORDS

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

def _structure_to_vhdl(structure_json: str) -> Tuple[str, Dict[str, str]]:
    """
    Converts a JSON topology into a VHDL architecture body.
    Returns the VHDL code and a mapping of {part_identifier: component_name}.
    """
    data = json.loads(structure_json)
    part_data = data['part']
    top_id = part_data['identifier']
    
    # 0. Build Port Type Map: (part_id, port_name) -> type_name
    port_type_map = {}
    for p in part_data['ports']:
        port_type_map[(top_id, p['name'])] = p.get('type_name', 'Logic')
    
    for inner in part_data['inner_parts']:
        for p in inner['ports']:
            port_type_map[(inner['identifier'], p['name'])] = p.get('type_name', 'Logic')

    # 1. Analyze Components to generate unique declarations
    # Map (class_name, frozenset(ports)) -> component_name
    comp_signatures = {}
    # Map part_id -> component_name
    part_comp_map = {}
    
    # Helper to create a signature for a component based on its ports
    def get_port_signature(ports_list):
        return frozenset((p['name'], p['direction'], p.get('type_name', 'Logic')) for p in ports_list)

    def get_component_name(class_name, port_signature):
        # Create a deterministic hash of the signature to ensure unique names for different configurations
        sorted_items = sorted(list(port_signature))
        s = f"{class_name}:{str(sorted_items)}".encode('utf-8')
        h = hashlib.md5(s).hexdigest()[:6]
        return f"{class_name}_{h}"

    for inner in part_data['inner_parts']:
        p_set = get_port_signature(inner['ports'])
        sig = (inner['class'], p_set)
        
        if sig not in comp_signatures:
            c_name = get_component_name(inner['class'], p_set)
            comp_signatures[sig] = c_name
        
        part_comp_map[inner['identifier']] = comp_signatures[sig]

    # 2. Analyze Signals (Nets)
    signals = {} # name -> type
    # Map (part_id, port_name) -> signal_name
    port_signal_map = {}
    
    # Initialize map with top-level ports (no signal declaration needed)
    for p in part_data['ports']:
        port_signal_map[(top_id, p['name'])] = p['name']
        
    for conn in part_data['connections']:
        src = conn['source']
        dst = conn['destination']
        
        src_key = (src['part_id'], src['port_id'])
        dst_key = (dst['part_id'], dst['port_id'])
        
        # Check if either side is already assigned to a signal/port
        sig_name = port_signal_map.get(src_key) or port_signal_map.get(dst_key)
        
        if not sig_name:
            # Create a new internal signal
            # Use the source part's local name to make it readable
            src_part_local = src['part_id'].split('.')[-1]
            sig_name = f"{src_part_local}_{src['port_id']}"
            
            src_type = port_type_map.get((src['part_id'], src['port_id']), 'Logic')
            signals[sig_name] = "INTEGER" if src_type == 'int' else "STD_LOGIC"
        
        port_signal_map[src_key] = sig_name
        port_signal_map[dst_key] = sig_name

    # 3. Generate VHDL Code
    lines = []
    
    # Component Declarations
    for (cls_name, p_set), comp_name in comp_signatures.items():
        lines.append(f"    component {comp_name} is")
        lines.append("        port (")
        # Recover port order from the first instance found matching this signature
        example_inner = next(i for i in part_data['inner_parts'] if part_comp_map[i['identifier']] == comp_name)
        p_list = example_inner['ports']
        for i, p in enumerate(p_list):
            p_dir = "in" if p['direction'] == "input" else "out"
            p_type_name = p.get('type_name', 'Logic')
            vhdl_type = "INTEGER" if p_type_name == 'int' else "STD_LOGIC"
            sep = ";" if i < len(p_list) - 1 else ""
            lines.append(f"            {p['name']} : {p_dir} {vhdl_type}{sep}")
        lines.append("        );")
        lines.append(f"    end component {comp_name};\n")

    # Signal Declarations
    for s_name, s_type in sorted(signals.items()):
        lines.append(f"    signal {s_name} : {s_type};")
    
    lines.append("\nbegin\n")
    
    # Component Instantiations
    for inner in part_data['inner_parts']:
        comp_name = part_comp_map[inner['identifier']]
        inst_name = inner['identifier'].split('.')[-1] + "_inst"
        lines.append(f"    {inst_name} : {comp_name}")
        lines.append("        port map (")
        p_list = inner['ports']
        for i, p in enumerate(p_list):
            # Default to 'open' if unconnected
            sig = port_signal_map.get((inner['identifier'], p['name']), 'open')
            sep = "," if i < len(p_list) - 1 else ""
            lines.append(f"            {p['name']} => {sig}{sep}")
        lines.append("        );\n")
        
    return "\n".join(lines), part_comp_map

def _generate_code(part: Part, language: str = "VHDL", entity_name: Optional[str] = None, architecture_name: str = "rtl", llm_client: Optional[Callable[[str], str]] = None) -> Tuple[str, Optional[Dict[str, str]]]:
    """
    Generates HDL code for a given Part.

    Args:
        part: The Part instance to generate code for.
        language: The target language (default: "VHDL").
        entity_name: The name of the entity/module. If None, defaults to the part's class name in lowercase.
        architecture_name: The name of the architecture (default: "rtl").
        llm_client: An optional function that accepts a prompt string and returns the generated architecture.

    Returns:
        Tuple[str, Optional[Dict[str, str]]]: The generated HDL code and a map of inner parts to component names (if structural).

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
        p_type = p.get_type() if hasattr(p, 'get_type') else None
        is_int = p_type is int or (hasattr(p_type, '__name__') and p_type.__name__ == 'int')
        vhdl_type = "INTEGER" if is_int else "STD_LOGIC"
        ports.append({
            "name": p.get_identifier(),
            "direction": "in" if p.get_direction() == Port.IN else "out",
            "type": vhdl_type
        })

    base_path = os.path.dirname(__file__)
    with open(os.path.join(base_path, 'VHDL', 'entity.vhd'), 'r') as f:
        entity_template_content = f.read()
    entity_template = Template(entity_template_content)
    
    entity_str = entity_template.render(entity_name=entity_name, ports=ports)
    
    # Check if the part is structural (has inner parts)
    if not part.get_description() == Part.BEHAVIORAL:
        try:
            from me.serializer import DiagramSerializer
            serializer = DiagramSerializer()
            structure_json = serializer.export_part_to_json(part)
            architecture_body_content, component_map = _structure_to_vhdl(structure_json)
            architecture_body = (
                f"\narchitecture {architecture_name} of {entity_name} is\n"
                f"{architecture_body_content}\n"
                f"end {architecture_name};"
            )
            return entity_str + "\n" + architecture_body, component_map
        except Exception as e:
            raise Exception(f"Error generating structural VHDL: {e}")

    if llm_client:
        try:
            behavior_code = inspect.getsource(part.behavior)
        except Exception:
            behavior_code = "-- Could not retrieve source code."
            
        attributes = {k: v for k, v in part.__dict__.items() if isinstance(v, (int, float, str, bool)) and not k.startswith('_')}

        # Prepend attributes as assignments to the behavior code
        # This helps the LLM resolve self.variable references to concrete values
        attr_header = []
        for k, v in attributes.items():
            val_str = f"'{v}'" if isinstance(v, str) else str(v)
            attr_header.append(f"self.{k} = {val_str}")
        if attr_header:
            behavior_code = "\n".join(attr_header) + "\n\n" + behavior_code

        context_lines = ["Entity Context:", "- **Ports**:"]
        for p in ports:
            context_lines.append(f"  - {p['name']}: {p['direction']} {p['type']}")
        if attributes:
            context_lines.append("- **Configuration**:")
            for k, v in attributes.items():
                context_lines.append(f"  - {k} = {v}")
        entity_context = "\n".join(context_lines)

        with open(os.path.join(base_path, 'VHDL', 'generation_prompt.txt'), 'r') as f:
            prompt_template_content = f.read()
        prompt_template = Template(prompt_template_content)
        prompt = prompt_template.render(
            behavior_code=behavior_code,
            entity_context=entity_context
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
    
    return entity_str + "\n" + architecture_body, None

def generate_code(part, language, output_dir, entity_name, architecture_name, llm, generate_build_script=False):
    import os
    import sys
    
    if llm and part.get_description() == Part.BEHAVIORAL:

        try:
            from google import genai
            from google.genai import errors
        except ImportError:
            print("Error: 'google-genai' library not found. Please run: pip install google-genai")
            return
        
        import time

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable is not set.")
            return

        client = genai.Client(api_key=api_key)
        model="gemini-2.5-flash-lite"

        def gemini_client(prompt: str) -> str:
            retries = 3
            while retries > 0:
                try:
                    response = client.models.generate_content(model=model, contents=prompt)
                    # Clean up Markdown code fences if the model returns them
                    text = response.text.replace("```vhdl", "").replace("```", "").strip()
                    
                    # Robust extraction of the process block to ignore potential entity wrappers
                    import re
                    match = re.search(r"(process.*?end process;)", text, re.IGNORECASE | re.DOTALL)
                    if match:
                        text = match.group(1)

                    return f"-- Generated by {model}\n{text}"
                except errors.ClientError as e:
                    if e.code == 429:
                        print("Quota exceeded (429). Retrying in 35 seconds...")
                        time.sleep(35)
                        retries -= 1
                    elif e.code == 404:
                        print(f"Error: Model '{model}' not found. Please verify the model name.")
                        print("Available models:")
                        try:
                            for m in client.models.list():
                                print(f" - {m.name}")
                        except Exception as list_e:
                            print(f"Failed to list models: {list_e}")
                        sys.exit(0)
                    else:
                        raise e
            raise Exception("Gemini API quota exceeded after retries.")
        
        llm_client = gemini_client
    
    else:

        llm_client = None

    entity_name_safe = entity_name
    if entity_name.lower() in VHDL_RESERVED_WORDS:
        s = entity_name.encode('utf-8')
        h = hashlib.md5(s).hexdigest()[:6]
        entity_name_safe = f"{entity_name}_{h}"

    architecture_name_safe = architecture_name
    if architecture_name.lower() in VHDL_RESERVED_WORDS:
        s = architecture_name.encode('utf-8')
        h = hashlib.md5(s).hexdigest()[:6]
        architecture_name_safe = f"{architecture_name}_{h}"

    try:
        code, component_map = _generate_code(part, language=language, entity_name=entity_name_safe, architecture_name=architecture_name_safe, llm_client=llm_client)
    except Exception as e:
        raise Exception(f"Code generation failed: {e}")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    filename = os.path.join(output_dir, f"{entity_name}.vhd")
    with open(filename, "w") as f:
        f.write(code)
    print(f"Code generated in {filename}")

    # Recursively generate code for inner parts
    if component_map:
        generated_entities = set()
        for child in part.get_parts():
            child_id = child.get_full_identifier()
            if child_id in component_map:
                child_entity_name = component_map[child_id]
                if child_entity_name not in generated_entities:
                    generate_code(child, language, output_dir, child_entity_name, "rtl", llm)
                    generated_entities.add(child_entity_name)

    if generate_build_script:
        base_path = os.path.dirname(__file__)
        with open(os.path.join(base_path, 'VHDL', 'compile.sh'), 'r') as f:
            script_template_content = f.read()
        script_template = Template(script_template_content)
        script_content = script_template.render(entity_name=entity_name_safe)
        
        script_filename = os.path.join(output_dir, "compile.sh")
        with open(script_filename, "w") as f:
            f.write(script_content)
        os.chmod(script_filename, 0o755)
        print(f"Build script generated in {script_filename}")