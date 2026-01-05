
architecture {{ architecture_name }} of {{ entity_name }} is
begin

    -- TODO: Implement behavior. Reference Python code:
{%- for line in behavior_lines %}
    -- {{ line }}
{%- endfor %}

end {{ architecture_name }};