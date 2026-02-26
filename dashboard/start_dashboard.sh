#!/bin/bash

echo "Starting The Live House - Instagram Account Dashboard"
echo ""
echo "Creating virtual environment if it doesn't exist..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing requirements..."
pip install -r requirements.txt

echo ""
echo "Starting dashboard server..."
python simple_app.py
