#!/bin/bash

# Change to the directory where the script is located
cd "$(dirname "$0")"

if [ -d ".cache" ]; then
    rm -rf .cache
    echo "Purged .cache"
else
    echo "No cache found."
fi