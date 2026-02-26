#!/bin/bash

# Setup script for Instagram automation

echo "Setting up Instagram automation environment..."

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

echo "Setup complete!"
echo ""
echo "To run the script:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Connect your Android device via USB and enable USB debugging"
echo "3. Run: python instagram_automation.py"
echo "   OR with IP: python instagram_automation.py <device_ip>"
echo ""
echo "Make sure Instagram is installed on your device!"