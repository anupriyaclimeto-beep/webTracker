#!/bin/bash
# Railway build script for Python API

echo "Building WebTracker API..."

# Install Python dependencies
pip install --upgrade pip
pip install -r api/requirements.txt

echo "Build complete!"
