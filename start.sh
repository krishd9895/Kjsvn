#!/bin/bash

# Exit on errors
set -eu

# Python buffers stdout. Without this, you won't see what you "print" in the Activity Logs
export PYTHONUNBUFFERED=true

# Virtual environment directory
VIRTUALENV=.data/venv

# Check if virtual environment exists, if not, create it
if [ ! -d $VIRTUALENV ]; then
  python3 -m venv $VIRTUALENV
fi

# Install pip if not installed
if [ ! -f $VIRTUALENV/bin/pip ]; then
  curl --silent --show-error --retry 5 https://bootstrap.pypa.io/get-pip.py | $VIRTUALENV/bin/python
fi

# Install requirements
$VIRTUALENV/bin/pip install -r requirements.txt

# Run the Flask web server
$VIRTUALENV/bin/python main.py
