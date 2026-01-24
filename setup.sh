#!/bin/bash
# setup.sh

echo "Setting up the application..."

# Create necessary directories
mkdir -p static
mkdir -p templates

# Copy CSS to static folder if it exists
if [ -f "style.css" ]; then
    cp style.css static/style.css
    echo "✅ Copied style.css to static folder"
fi

# Install dependencies
pip install -r requirements.txt

echo "✅ Setup complete!"