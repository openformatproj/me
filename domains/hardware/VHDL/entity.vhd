library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity {{ entity_name }} is
    Port (
{%- for port in ports %}
           {{ port.name }} : {{ port.direction }} {{ port.type }}{{ ";" if not loop.last else "" }}
{%- endfor %}
    );
end {{ entity_name }};