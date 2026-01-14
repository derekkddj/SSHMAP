"""
Basic tests for the SSHMAP Web Interface.

These tests verify that the Flask app initializes correctly and that
the API endpoints are properly configured.
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_web_app_imports():
    """Test that the web app can be imported without errors."""
    try:
        import web_app
        assert web_app.app is not None
    except ImportError as e:
        pytest.fail(f"Failed to import web_app: {e}")


def test_flask_app_exists():
    """Test that Flask app instance is created."""
    from web_app import app
    assert app is not None
    assert app.name == 'web_app'


def test_routes_registered():
    """Test that all expected routes are registered."""
    from web_app import app
    
    # Get all registered routes
    routes = [str(rule) for rule in app.url_map.iter_rules()]
    
    # Check for expected endpoints
    expected_routes = [
        '/',
        '/api/graph',
        '/api/search',
        '/api/path',
        '/api/node/<int:node_id>',
        '/api/edge/<int:edge_id>',
        '/api/hosts'
    ]
    
    for route in expected_routes:
        # Note: Flask adds some variations, so we check if the base path exists
        assert any(route.replace('<int:node_id>', '<node_id>') in r or 
                   route.replace('<int:edge_id>', '<edge_id>') in r or
                   route in r for r in routes), f"Route {route} not found in {routes}"


def test_templates_directory_exists():
    """Test that templates directory exists."""
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    assert os.path.exists(templates_dir), "templates directory does not exist"
    assert os.path.isdir(templates_dir), "templates is not a directory"


def test_static_directory_exists():
    """Test that static directory exists with required subdirectories."""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
    assert os.path.exists(static_dir), "static directory does not exist"
    assert os.path.isdir(static_dir), "static is not a directory"
    
    # Check for subdirectories
    css_dir = os.path.join(static_dir, 'css')
    js_dir = os.path.join(static_dir, 'js')
    
    assert os.path.exists(css_dir), "css directory does not exist"
    assert os.path.exists(js_dir), "js directory does not exist"


def test_index_template_exists():
    """Test that index.html template exists."""
    template_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'templates', 
        'index.html'
    )
    assert os.path.exists(template_file), "index.html template does not exist"


def test_javascript_file_exists():
    """Test that app.js JavaScript file exists."""
    js_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'static', 
        'js', 
        'app.js'
    )
    assert os.path.exists(js_file), "app.js file does not exist"


def test_css_file_exists():
    """Test that style.css file exists."""
    css_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'static', 
        'css', 
        'style.css'
    )
    assert os.path.exists(css_file), "style.css file does not exist"


def test_launcher_script_exists():
    """Test that the launcher script exists and is executable."""
    launcher = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'sshmap_web.py'
    )
    assert os.path.exists(launcher), "sshmap_web.py launcher does not exist"
    # Check if file is executable (on Unix-like systems)
    if os.name != 'nt':  # Not Windows
        assert os.access(launcher, os.X_OK), "sshmap_web.py is not executable"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
