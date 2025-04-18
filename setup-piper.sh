#!/bin/bash
set -e  # Exit immediately on error

echo "🔧 Installing Piper..."

# Create working directory
WORKDIR=/tmp/piper-install
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# Download Piper ARM64 release
echo "📥 Downloading Piper..."
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_arm64.tar.gz

# Extract
echo "📦 Extracting..."
tar -xzf piper_arm64.tar.gz

# Move binary
echo "🚀 Installing binary to /usr/local/bin"
mv piper/piper /usr/local/bin/piper
chmod +x /usr/local/bin/piper

# Move shared libraries
echo "🔗 Installing shared libraries to /usr/local/lib"
cp piper/lib*.so* /usr/local/lib/

# Update dynamic linker
echo "📚 Running ldconfig"
ldconfig

# Cleanup
echo "🧹 Cleaning up"
rm -rf "$WORKDIR"

echo "✅ Piper installed!"

