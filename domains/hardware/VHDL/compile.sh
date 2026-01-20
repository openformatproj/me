#!/bin/bash
set -e

# Clean up previous artifacts
rm -f *.cf {{ entity_name }}

echo "Analyzing VHDL files..."
ghdl -a --std=08 *.vhd

echo "Elaborating top-level entity '{{ entity_name }}'..."
ghdl -e --std=08 {{ entity_name }}

echo "Compilation successful."
