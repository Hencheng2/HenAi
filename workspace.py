# workspace.py - Workspace management for HenAi

import os
import json
from datetime import datetime
from flask import jsonify, request
from werkzeug.utils import secure_filename

# Constants
WORKSPACE_FILE = 'workspace.json'

def load_workspace():
    """Load workspace structure from file"""
    try:
        if os.path.exists(WORKSPACE_FILE):
            with open(WORKSPACE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading workspace: {e}")
    return {"folders": []}  # Folders will be stored in order (newest first)

def save_workspace(workspace):
    """Save workspace structure to file"""
    try:
        with open(WORKSPACE_FILE, 'w', encoding='utf-8') as f:
            json.dump(workspace, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving workspace: {e}")

def build_folder_tree(folder, base_path=''):
    """Recursively build folder tree with file contents"""
    tree = {
        'name': base_path.split('/')[-1] if base_path else 'Root',
        'path': base_path,
        'type': 'folder',
        'children': []
    }
    
    # Add subfolders
    for subfolder in folder.get('folders', []):
        subfolder_path = base_path + '/' + subfolder['name'] if base_path else subfolder['name']
        tree['children'].append(build_folder_tree(subfolder, subfolder_path))
    
    # Add files
    for file_item in folder.get('files', []):
        file_path = base_path + '/' + file_item['name'] if base_path else file_item['name']
        tree['children'].append({
            'name': file_item['name'],
            'path': file_path,
            'type': 'file',
            'content': file_item.get('content', ''),
            'size': len(file_item.get('content', '')),
            'updated_at': file_item.get('updated_at', '')
        })
    
    return tree

def build_folder_context(folder, base_path=''):
    """Build a text representation of folder structure and contents"""
    context = f"\n=== FOLDER: {base_path if base_path else 'Root'} ===\n"
    
    # Add subfolders
    for subfolder in folder.get('folders', []):
        subfolder_path = base_path + '/' + subfolder['name'] if base_path else subfolder['name']
        context += f"\n📁 Folder: {subfolder['name']}/ (path: {subfolder_path})\n"
        context += build_folder_context(subfolder, subfolder_path)
    
    # Add files with content
    for file_item in folder.get('files', []):
        file_path = base_path + '/' + file_item['name'] if base_path else file_item['name']
        file_ext = file_item['name'].split('.')[-1].lower()
        context += f"\n--- FILE: {file_path} ({file_ext}) ---\n"
        context += file_item.get('content', '')
        context += f"\n--- END FILE: {file_path} ---\n"
    
    return context

def get_file_content_from_workspace(file_path):
    """Helper to get file content from workspace"""
    workspace = load_workspace()
    
    parts = file_path.split('/')
    file_name = parts[-1]
    folder_parts = parts[:-1] if len(parts) > 1 else []
    
    current = workspace
    for folder_name in folder_parts:
        found = False
        for folder in current.get('folders', []):
            if folder.get('name') == folder_name:
                current = folder
                found = True
                break
        if not found:
            return None
    
    files = current.get('files', [])
    for file_item in files:
        if file_item.get('name') == file_name:
            return file_item.get('content', '')
    
    return None

def navigate_to_folder(workspace, folder_path):
    """Navigate to a folder given its path"""
    if not folder_path:
        return workspace
    
    parts = folder_path.split('/')
    current = workspace
    
    for part in parts:
        found = False
        for folder in current.get('folders', []):
            if folder.get('name') == part:
                current = folder
                found = True
                break
        if not found:
            return None
    
    return current

def find_file_in_folder(folder, file_name):
    """Find a file in a folder by name"""
    for file_item in folder.get('files', []):
        if file_item.get('name') == file_name:
            return file_item
    return None

# ============= WORKSPACE ROUTE HANDLERS =============

def register_workspace_routes(app):
    """Register all workspace routes with the Flask app"""
    
    @app.route('/api/workspace', methods=['GET'])
    def get_workspace():
        """Get the entire workspace structure"""
        workspace = load_workspace()
        return jsonify(workspace)

    @app.route('/api/workspace/folder', methods=['POST'])
    def create_folder():
        """Create a new folder"""
        data = request.json
        folder_name = data.get('name', '').strip()
        parent_path = data.get('parent_path', '')
        
        if not folder_name:
            return jsonify({'error': 'Folder name is required'}), 400
        
        workspace = load_workspace()
        
        # Navigate to parent folder if specified
        if parent_path:
            parts = parent_path.split('/') if parent_path else []
            current = workspace
            for part in parts:
                found = False
                for folder in current.get('folders', []):
                    if folder.get('name') == part:
                        current = folder
                        found = True
                        break
                if not found:
                    return jsonify({'error': f'Parent folder "{parent_path}" not found'}), 404
            parent = current
        else:
            parent = workspace
        
        # Ensure folders list exists
        if 'folders' not in parent:
            parent['folders'] = []
        
        # Check if folder already exists
        for folder in parent['folders']:
            if folder.get('name') == folder_name:
                return jsonify({'error': 'Folder already exists'}), 400
        
        # Create new folder (newest at the beginning of the list)
        new_folder = {
            'name': folder_name,
            'created_at': datetime.now().isoformat(),
            'folders': [],
            'files': []
        }
        parent['folders'].insert(0, new_folder)  # Insert at beginning for newest first
        
        save_workspace(workspace)
        return jsonify({'success': True, 'folder': new_folder})

    @app.route('/api/workspace/file', methods=['POST'])
    def create_file():
        """Create a new file in a folder"""
        data = request.json
        file_name = data.get('name', '').strip()
        folder_path = data.get('folder_path', '')
        content = data.get('content', '')
        
        if not file_name:
            return jsonify({'error': 'File name is required'}), 400
        
        workspace = load_workspace()
        
        # Navigate to the target folder
        if folder_path:
            parts = folder_path.split('/') if folder_path else []
            current = workspace
            for part in parts:
                found = False
                for folder in current.get('folders', []):
                    if folder.get('name') == part:
                        current = folder
                        found = True
                        break
                if not found:
                    return jsonify({'error': f'Folder "{folder_path}" not found'}), 404
            target_folder = current
        else:
            target_folder = workspace
        
        # Ensure files list exists
        if 'files' not in target_folder:
            target_folder['files'] = []
        
        # Check if file already exists
        for file_item in target_folder['files']:
            if file_item.get('name') == file_name:
                return jsonify({'error': 'File already exists'}), 400
        
        # Create new file (newest at the beginning of the list)
        new_file = {
            'name': file_name,
            'content': content,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        target_folder['files'].insert(0, new_file)  # Insert at beginning for newest first
        
        save_workspace(workspace)
        return jsonify({'success': True, 'file': new_file})

    @app.route('/api/workspace/file/<path:file_path>', methods=['PUT'])
    def update_file(file_path):
        """Update file content"""
        data = request.json
        content = data.get('content', '')
        
        workspace = load_workspace()
        
        # Parse file path (format: "folder1/subfolder/file.txt" or "file.txt")
        parts = file_path.split('/')
        file_name = parts[-1]
        folder_parts = parts[:-1] if len(parts) > 1 else []
        
        # Navigate to the folder containing the file
        current = workspace
        for folder_name in folder_parts:
            found = False
            for folder in current.get('folders', []):
                if folder.get('name') == folder_name:
                    current = folder
                    found = True
                    break
            if not found:
                return jsonify({'error': f'Folder "{folder_name}" not found'}), 404
        
        # Find and update the file
        files = current.get('files', [])
        for file_item in files:
            if file_item.get('name') == file_name:
                file_item['content'] = content
                file_item['updated_at'] = datetime.now().isoformat()
                save_workspace(workspace)
                return jsonify({'success': True, 'file': file_item})
        
        return jsonify({'error': 'File not found'}), 404

    @app.route('/api/workspace/file/<path:file_path>', methods=['DELETE'])
    def delete_file(file_path):
        """Delete a file"""
        workspace = load_workspace()
        
        # Parse file path
        parts = file_path.split('/')
        file_name = parts[-1]
        folder_parts = parts[:-1] if len(parts) > 1 else []
        
        # Navigate to the folder containing the file
        current = workspace
        for folder_name in folder_parts:
            found = False
            for folder in current.get('folders', []):
                if folder.get('name') == folder_name:
                    current = folder
                    found = True
                    break
            if not found:
                return jsonify({'error': f'Folder "{folder_name}" not found'}), 404
        
        # Find and delete the file
        files = current.get('files', [])
        for i, file_item in enumerate(files):
            if file_item.get('name') == file_name:
                del files[i]
                save_workspace(workspace)
                return jsonify({'success': True})
        
        return jsonify({'error': 'File not found'}), 404

    @app.route('/api/workspace/folder/<path:folder_path>', methods=['DELETE'])
    def delete_folder(folder_path):
        """Delete a folder and all its contents"""
        workspace = load_workspace()
        
        # Parse folder path
        parts = folder_path.split('/') if folder_path else []
        
        if not parts:
            return jsonify({'error': 'Cannot delete root'}), 400
        
        folder_name = parts[-1]
        parent_parts = parts[:-1]
        
        # Navigate to parent
        current = workspace
        for parent_name in parent_parts:
            found = False
            for folder in current.get('folders', []):
                if folder.get('name') == parent_name:
                    current = folder
                    found = True
                    break
            if not found:
                return jsonify({'error': f'Parent folder not found'}), 404
        
        # Find and delete the folder
        folders = current.get('folders', [])
        for i, folder in enumerate(folders):
            if folder.get('name') == folder_name:
                del folders[i]
                save_workspace(workspace)
                return jsonify({'success': True})
        
        return jsonify({'error': 'Folder not found'}), 404

    @app.route('/api/workspace/file/<path:file_path>/content', methods=['GET'])
    def get_file_content(file_path):
        """Get the full content of a file for the IDE"""
        workspace = load_workspace()
        
        # Parse file path
        parts = file_path.split('/')
        file_name = parts[-1]
        folder_parts = parts[:-1] if len(parts) > 1 else []
        
        # Navigate to the folder containing the file
        current = workspace
        for folder_name in folder_parts:
            found = False
            for folder in current.get('folders', []):
                if folder.get('name') == folder_name:
                    current = folder
                    found = True
                    break
            if not found:
                return jsonify({'error': f'Folder not found'}), 404
        
        # Find the file
        files = current.get('files', [])
        for file_item in files:
            if file_item.get('name') == file_name:
                return jsonify({
                    'success': True,
                    'content': file_item.get('content', ''),
                    'name': file_name,
                    'path': file_path
                })
        
        return jsonify({'error': 'File not found'}), 404

    @app.route('/api/workspace/folder_tree', methods=['POST'])
    def get_folder_tree():
        """Get the full tree structure of a root folder for AI context"""
        data = request.json
        folder_path = data.get('folder_path', '')
        
        workspace = load_workspace()
        
        # Navigate to the folder
        if folder_path:
            parts = folder_path.split('/') if folder_path else []
            current = workspace
            for part in parts:
                found = False
                for folder in current.get('folders', []):
                    if folder.get('name') == part:
                        current = folder
                        found = True
                        break
                if not found:
                    return jsonify({'error': f'Folder "{folder_path}" not found'}), 404
        else:
            current = workspace
        
        # Build folder tree with file contents
        tree = build_folder_tree(current, folder_path)
        
        return jsonify({
            'success': True,
            'tree': tree
        })

    # ============= TERMINAL SESSION MANAGEMENT =============
    
    # Store active terminal sessions per workspace folder
    active_terminal_sessions = {}
    
    @app.route('/api/workspace/terminal/start', methods=['POST'])
    def start_terminal_session():
        """Start a terminal session for a specific workspace folder"""
        data = request.json
        folder_path = data.get('folder_path', '')
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'Session ID required'}), 400
        
        # Get the actual workspace root (where workspace.json is)
        workspace_base = os.path.dirname(os.path.abspath(__file__))
        
        # If folder_path is provided, navigate to that subfolder within workspace
        if folder_path:
            # Clean the folder path - remove any Windows drive letters
            clean_path = re.sub(r'^[A-Za-z]:[/\\]', '', folder_path)
            clean_path = clean_path.replace('HenAi:\\Workspace\\', '').replace('HenAi:\\', '')
            workspace_dir = os.path.join(workspace_base, clean_path)
        else:
            workspace_dir = workspace_base
        
        # Ensure directory exists
        if not os.path.exists(workspace_dir):
            os.makedirs(workspace_dir, exist_ok=True)
        
        # Import terminal emulator
        from terminal import TerminalEmulator
        
        # Create terminal session with workspace root set
        terminal = TerminalEmulator()
        terminal.workspace_root = workspace_base
        terminal.current_directory = workspace_dir
        os.chdir(workspace_dir)
        
        # Store session
        if folder_path not in active_terminal_sessions:
            active_terminal_sessions[folder_path] = {}
        active_terminal_sessions[folder_path][session_id] = {
            'terminal': terminal,
            'started_at': datetime.now().isoformat(),
            'folder_path': folder_path,
            'is_active': True
        }
        
        # Return friendly path for display
        rel_path = os.path.relpath(workspace_dir, workspace_base)
        if rel_path == '.':
            friendly_path = "HenAi:\\Workspace"
        else:
            friendly_path = f"HenAi:\\Workspace\\{rel_path.replace(os.sep, '\\')}"
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'cwd': friendly_path,
            'raw_cwd': workspace_dir,
            'message': f'Terminal started in {friendly_path}'
        })
    
    @app.route('/api/workspace/terminal/execute', methods=['POST'])
    def execute_terminal_command():
        """Execute a command in the terminal session"""
        data = request.json
        folder_path = data.get('folder_path', '')
        session_id = data.get('session_id')
        command = data.get('command', '')
        
        if not session_id:
            return jsonify({'error': 'Session ID required'}), 400
        
        # Check if session exists
        if folder_path not in active_terminal_sessions:
            return jsonify({'error': 'No active terminal session for this folder'}), 404
        
        if session_id not in active_terminal_sessions[folder_path]:
            return jsonify({'error': 'Invalid session ID'}), 404
        
        session = active_terminal_sessions[folder_path][session_id]
        terminal = session['terminal']
        
        if not session['is_active']:
            return jsonify({'error': 'Terminal session is closed'}), 400
        
        # Execute command
        result = terminal.execute_and_get_output(command)
        
        return jsonify({
            'success': result['success'],
            'output': result['output'],
            'error': result['error'],
            'exit_code': result['exit_code'],
            'cwd': terminal.current_directory
        })
    
    @app.route('/api/workspace/terminal/stop', methods=['POST'])
    def stop_terminal_session():
        """Stop and close a terminal session"""
        data = request.json
        folder_path = data.get('folder_path', '')
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'Session ID required'}), 400
        
        if folder_path in active_terminal_sessions:
            if session_id in active_terminal_sessions[folder_path]:
                # Mark as inactive and remove
                active_terminal_sessions[folder_path][session_id]['is_active'] = False
                del active_terminal_sessions[folder_path][session_id]
                
                # Clean up empty folder entries
                if not active_terminal_sessions[folder_path]:
                    del active_terminal_sessions[folder_path]
                
                return jsonify({'success': True, 'message': 'Terminal session closed'})
        
        return jsonify({'error': 'Terminal session not found'}), 404
    
    @app.route('/api/workspace/terminal/status', methods=['GET'])
    def get_terminal_status():
        """Check if a terminal session is active for a folder"""
        folder_path = request.args.get('folder_path', '')
        
        is_active = folder_path in active_terminal_sessions and len(active_terminal_sessions[folder_path]) > 0
        
        # Get active sessions info
        sessions = []
        if is_active:
            for sess_id, sess in active_terminal_sessions[folder_path].items():
                sessions.append({
                    'session_id': sess_id,
                    'started_at': sess['started_at'],
                    'cwd': sess['terminal'].current_directory
                })
        
        return jsonify({
            'is_active': is_active,
            'sessions': sessions,
            'folder_path': folder_path
        })