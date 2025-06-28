#!/bin/bash

# Script to create a properly structured Kodi plugin zip file
# Usage: ./create_plugin_zip.sh

# Get plugin ID from addon.xml
PLUGIN_ID=$(grep 'addon id=' addon.xml | sed 's/.*id="\([^"]*\)".*/\1/')
echo "Creating zip for plugin ID: $PLUGIN_ID"

# Clean up any existing temp directories
rm -rf temp/

# Create temp directory with plugin ID as folder name
mkdir -p temp/$PLUGIN_ID

# Copy all plugin files to the temp directory
cp addon.xml temp/$PLUGIN_ID/
cp main.py temp/$PLUGIN_ID/
cp md5crypt.py temp/$PLUGIN_ID/
cp series_manager.py temp/$PLUGIN_ID/
cp yawsp.py temp/$PLUGIN_ID/
cp -r resources/ temp/$PLUGIN_ID/
cp LICENSE temp/$PLUGIN_ID/
cp README.md temp/$PLUGIN_ID/

# Create the zip file in the plugin directory
cd temp
zip -r ../plugin/$PLUGIN_ID.zip $PLUGIN_ID/
cd ..

# Clean up temp directory
rm -rf temp/

echo "Created: plugin/$PLUGIN_ID.zip"
echo "Ready to install in Kodi!"