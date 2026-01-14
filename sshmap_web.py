#!/usr/bin/env python3
"""
Launcher script for SSHMAP Web Interface.
This script provides an easy way to start the web application.
"""

import sys
import os

# Add the parent directory to the path to allow imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the web app
from web_app import app, db

if __name__ == '__main__':
    try:
        print()
        print("=" * 70)
        print("🔐 SSHMAP Web Interface")
        print("=" * 70)
        print()
        print("Starting web server...")
        print("  ➜ Local:   http://127.0.0.1:5000")
        print()
        print("📊 Connect to your Neo4j database and explore SSH connections")
        print("🔍 Search, visualize, and find paths in your network")
        print()
        print("Press Ctrl+C to stop the server")
        print("=" * 70)
        print()
        
        # Run the Flask app
        app.run(host='127.0.0.1', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n\n✓ Server stopped by user")
        print("Thanks for using SSHMAP!")
    except Exception as e:
        print(f"\n✗ Error starting server: {e}")
        print("\nMake sure:")
        print("  1. Neo4j is running (default: bolt://localhost:7687)")
        print("  2. Config file exists at ~/.sshmap/config.yml")
        print("  3. All dependencies are installed (pip install -r requirements.txt)")
        sys.exit(1)
    finally:
        # Close database connection
        try:
            db.close()
        except:
            pass
