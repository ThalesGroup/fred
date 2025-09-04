#!/usr/bin/env python3
"""
Security check script to verify FastAPI routes are properly secured with authentication.
Analyzes routes in FastAPI backends to identify endpoints missing authentication dependencies.
"""

import inspect
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional


def setup_backend_environment(backend_dir: Path):
    """Setup environment to import the FastAPI app."""
    app_dir = backend_dir / "app"
    config_dir = backend_dir / "config"
    
    # Validate backend directory structure
    if not app_dir.exists() or not (app_dir / "main.py").exists():
        raise FileNotFoundError(f"Could not find app/main.py in {backend_dir}")
    
    if not config_dir.exists() or not (config_dir / "configuration.yaml").exists():
        raise FileNotFoundError(f"Could not find config/configuration.yaml in {backend_dir}")
    
    # Add the app directory to Python path
    sys.path.insert(0, str(app_dir))
    
    # Set required environment variables
    os.environ.setdefault("ENV_FILE", str(config_dir / ".env"))
    os.environ.setdefault("CONFIG_FILE", str(config_dir / "configuration.yaml"))
    os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key-for-static-analysis")


def get_route_function_info(app, path: str, method: str) -> Optional[tuple[str, int]]:
    """Get the file and line number for a route's handler function."""
    try:
        # Find the route in FastAPI app
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                if route.path == path and method.upper() in route.methods:
                    # Get the endpoint function
                    endpoint = route.endpoint
                    if endpoint:
                        # Get source file and line number
                        source_file = inspect.getfile(endpoint)
                        line_number = inspect.getsourcelines(endpoint)[1]
                        
                        # Convert to relative path from backend directory
                        backend_dir = Path.cwd()
                        try:
                            rel_path = Path(source_file).relative_to(backend_dir)
                            return str(rel_path), line_number
                        except ValueError:
                            # If we can't make it relative, return absolute path
                            return source_file, line_number
    except Exception:
        pass
    
    return None


def has_auth_dependency(app, path: str, method: str) -> bool:
    """Check if a route has authentication dependency by inspecting the function signature."""
    try:
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                if route.path == path and method.upper() in route.methods:
                    # Check if route has security dependencies
                    if hasattr(route, 'dependencies') and route.dependencies:
                        # Look for get_current_user in dependencies
                        for dep in route.dependencies:
                            if hasattr(dep, 'dependency'):
                                dep_str = str(dep.dependency)
                                if 'get_current_user' in dep_str:
                                    return True
                    
                    # Also check function signature for auth parameters
                    if route.endpoint:
                        sig = inspect.signature(route.endpoint)
                        for param_name, param in sig.parameters.items():
                            if param.annotation and 'KeycloakUser' in str(param.annotation):
                                return True
                            if param.default and 'get_current_user' in str(param.default):
                                return True
    except Exception:
        pass
    
    return False


def get_exempt_routes() -> Set[str]:
    """Return set of routes that are exempt from authentication requirements."""
    return {
        # FastAPI auto routes
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc", 
        "/openapi.json",
        # Kubernetes monitoring routes
        "/healthz",
        "/ready",
        # Agentic specific routes
        "/config/frontend_settings"
    }


def check_route_security(backend_dir: Path) -> tuple[bool, List[Dict]]:
    """
    Check route security for a backend by introspecting the FastAPI app.
    
    Returns:
        tuple: (is_secure, unsecured_routes)
    """
    try:
        setup_backend_environment(backend_dir)
        
        # Import and create the FastAPI app
        from main import create_app
        app = create_app()
        
        exempt_routes = get_exempt_routes()
        unsecured_routes = []
        
        # Inspect all routes in the app
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                for method in route.methods:
                    if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        path = route.path
                        
                        # Skip exempt routes
                        if any(path.endswith(exempt) or path == exempt for exempt in exempt_routes):
                            continue
                        
                        # Check if route is secured
                        if not has_auth_dependency(app, path, method):
                            # Get file and line information
                            file_info = get_route_function_info(app, path, method)
                            
                            route_dict = {
                                "path": path,
                                "method": method.upper(),
                                "summary": getattr(route, 'summary', '') or '',
                                "tags": getattr(route, 'tags', []) or []
                            }
                            
                            if file_info:
                                route_dict["controller_file"], route_dict["line_number"] = file_info
                            else:
                                route_dict["controller_file"] = None
                                route_dict["line_number"] = None
                            
                            unsecured_routes.append(route_dict)
        
        return len(unsecured_routes) == 0, unsecured_routes
        
    except Exception as e:
        print(f"❌ Error checking route security for {backend_dir.name}: {e}")
        import traceback
        traceback.print_exc()
        return False, []


def main():
    """Main entry point for route security check."""
    backend_dir = Path.cwd()
    backend_name = backend_dir.name
    
    print(f"🔒 Checking route security for {backend_name}...")
    
    is_secure, unsecured_routes = check_route_security(backend_dir)
    
    if is_secure:
        print(f"✅ All routes in {backend_name} are properly secured!")
        return 0
    else:
        print(f"❌ Found {len(unsecured_routes)} unsecured route(s) in {backend_name}:")
        for route in unsecured_routes:
            print(f"  - {route['method']} {route['path']}")
            if route.get('summary'):
                print(f"    Summary: {route['summary']}")
            if route.get('controller_file') and route.get('line_number'):
                print(f"    File: {route['controller_file']}:{route['line_number']}")
            else:
                print("    File: <location not found>")
            
            print("")

        print("\nTo secure these routes, add: user: KeycloakUser = Depends(get_current_user)")
        return 1


if __name__ == "__main__":
    sys.exit(main())