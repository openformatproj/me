#!/bin/bash

if [ -d "{{ output_dir }}/.cache" ]; then
    rm -rf {{ output_dir }}/.cache
    echo "Purged {{ output_dir }}/.cache"
elif [ -d ".cache" ]; then
    rm -rf .cache
    echo "Purged .cache"
else
    echo "No cache found."
fi