#!/bin/bash
echo "Starting build..."

# Create static folder
mkdir -p static

# Copy CSS to static folder if it exists
if [ -f "style.css" ]; then
    cp style.css static/style.css
    echo "✅ style.css copied to static folder"
fi

# Install dependencies
pip install -r requirements.txt

echo "✅ Build complete!"