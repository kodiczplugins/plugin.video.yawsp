#!/bin/bash

# Script to create a properly structured Kodi plugin zip file
# Usage: ./create_plugin_zip.sh

# Get plugin ID from addon.xml
PLUGIN_ID=$(grep 'addon id=' addon.xml | sed 's/.*id="\([^"]*\)".*/\1/')
ZIP_FOLDER="plugin.video.yawsp-master"
echo "Creating zip for plugin ID: $PLUGIN_ID"

# Clean up any existing temp directories
rm -rf temp/

# Create temp directory with hardcoded -master suffix (zip folder name)
mkdir -p temp/$ZIP_FOLDER

# Copy all plugin files to the temp directory
cp addon.xml temp/$ZIP_FOLDER/
cp main.py temp/$ZIP_FOLDER/
cp md5crypt.py temp/$ZIP_FOLDER/
cp series_manager.py temp/$ZIP_FOLDER/
cp yawsp.py temp/$ZIP_FOLDER/
mkdir -p temp/$ZIP_FOLDER/resources
cp -r resources temp/$ZIP_FOLDER/
cp LICENSE temp/$ZIP_FOLDER/
cp README.md temp/$ZIP_FOLDER/

# Create the zip file in the plugin directory with -master suffix
cd temp
zip -r ../plugin/$ZIP_FOLDER.zip $ZIP_FOLDER/
cd ..

# Clean up temp directory
rm -rf temp/

echo "Created: plugin/$ZIP_FOLDER.zip"
echo "Ready to install in Kodi!"