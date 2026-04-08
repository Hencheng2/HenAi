# app.py - Chat & Search Only Version (No Document Features)

import os
import json
import re
import uuid
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import requests
from datetime import datetime
import base64
from docs import DocumentProcessor
import io

# Import AI functions from models.py
from models import (
    query_ai_with_fallback,
    generate_chat_title,
    is_code_generation_request,
    execute_python_code,
    search_web,
    extract_web_content,
    analyze_image_with_ai,
    call_pollinations_ai
)

# Import workspace functions from workspace.py
from workspace import register_workspace_routes

# Import free image generator
from image import FreeImageGenerator

# Import media handler
from media import media_handler

from vision import get_vision_model

# Import terminal blueprint
from terminal import create_terminal_blueprint

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
CORS(app)

# Register terminal routes
app.register_blueprint(create_terminal_blueprint(app))

# Ensure directories exist
os.makedirs('generated_images', exist_ok=True)

# Initialize free image generator
image_generator = FreeImageGenerator(output_dir="generated_images")

CONVERSATIONS_FILE = 'conversations.json'

# Allowed file extensions for attachments
ALLOWED_EXTENSIONS = {
    'txt', 'md', 'py', 'js', 'html', 'css', 'json', 'xml', 'csv',
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp',
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'mp3', 'wav', 'ogg', 'flac', 'm4a',
    'mp4', 'avi', 'mov', 'mkv', 'webm',
    'zip', 'rar', '7z', 'tar', 'gz', 'bz2',
    'java', 'c', 'cpp', 'h', 'rb', 'php', 'go', 'rs', 'swift', 'kt'
}

def sanitize_filename(text):
    """Sanitize text to be safe for use in filenames"""
    if not text:
        return "New Chat"
    text = ''.join(char for char in text if char.isprintable() and char not in '\n\r\t')
    replacements = {
        '/': '-', '\\': '-', ':': '-', '*': '-', '?': '-',
        '"': "'", '<': '-', '>': '-', '|': '-'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.strip()[:100]
    return text if text else "New Chat"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_conversations():
    try:
        if os.path.exists(CONVERSATIONS_FILE):
            with open(CONVERSATIONS_FILE, 'r', encoding='utf-8') as f:
                conversations = json.load(f)
                for conv_id, conv_data in conversations.items():
                    if 'versions' not in conv_data:
                        conv_data['versions'] = {}
                    if 'current_version_index' not in conv_data:
                        conv_data['current_version_index'] = {}
                    if 'branch_root' not in conv_data:
                        conv_data['branch_root'] = None
                return conversations
    except Exception as e:
        print(f"Error loading conversations: {e}")
    return {}

def save_conversations(conversations):
    try:
        with open(CONVERSATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(conversations, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving conversations: {e}")

conversations = load_conversations()

def extract_text_from_file(file_content, filename):
    """Extract text from uploaded files"""
    try:
        # Simple text extraction for common file types
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        
        if ext in ['txt', 'md', 'py', 'js', 'html', 'css', 'json', 'xml', 'csv']:
            try:
                return file_content.decode('utf-8', errors='replace')
            except:
                return file_content.decode('latin-1', errors='replace')
        else:
            # For binary files, just note the type
            return f"[Binary file: {filename} - {len(file_content)} bytes]"
        
    except Exception as e:
        print(f"Error extracting text: {e}")
        return f"[Error extracting from {filename}: {str(e)}]"

def is_image_generation_request(message):
    """Detect if a user message is requesting image generation"""
    if not message:
        return False
    
    message_lower = message.lower()
    
    analysis_keywords = [
        'analyze', 'analyse', 'what is', 'what\'s', 'tell me about', 
        'describe', 'explain', 'read this', 'look at', 'examine'
    ]
    
    for keyword in analysis_keywords:
        if keyword in message_lower:
            return False
    
    image_keywords = [
        'generate image', 'create image', 'make image', 'draw image',
        'generate picture', 'create picture', 'make picture',
        'generate art', 'create art',
        'ai image', 'ai art',
        'image of', 'picture of',
        'draw me', 'generate me', 'create me'
    ]
    
    for keyword in image_keywords:
        if keyword in message_lower:
            return True
    
    words = message_lower.split()
    if len(words) <= 5 and any(word in ['image', 'picture', 'photo', 'art'] for word in words):
        if not any(word in message_lower for word in ['this', 'the', 'that', 'attached']):
            return True
    
    return False

def extract_image_prompt(message):
    """Extract the actual image prompt from the message"""
    message_lower = message.lower()
    
    prefixes = [
        'generate image of', 'create image of', 'make image of', 'draw image of',
        'generate picture of', 'create picture of', 'make picture of',
        'image of', 'picture of',
        'draw me', 'generate me', 'create me',
        'generate an image of', 'create an image of'
    ]
    
    prompt = message.strip()
    for prefix in prefixes:
        if message_lower.startswith(prefix):
            prompt = message[len(prefix):].strip()
            break
    
    prompt = prompt.strip('.,!?;:')
    
    if len(prompt) < 3:
        prompt = message.strip()
    
    return prompt

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '')
    conversation_id = data.get('conversation_id')
    regenerate = data.get('regenerate', False)
    regenerate_from = data.get('regenerate_from')
    attached_files = data.get('attached_files', [])

    if not conversation_id or conversation_id not in conversations:
        conversation_id = str(uuid.uuid4())
        conversations[conversation_id] = {
            'id': conversation_id,
            'messages': [],
            'title': 'New Chat',
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'versions': {},
            'current_version_index': {},
            'branch_root': None
        }

    conv = conversations[conversation_id]

    if 'versions' not in conv:
        conv['versions'] = {}
    if 'current_version_index' not in conv:
        conv['current_version_index'] = {}
    if 'branch_root' not in conv:
        conv['branch_root'] = None

    # Handle pending attachments
    if 'pending_attachments' in conv and conv['pending_attachments']:
        if message:
            if not attached_files:
                attached_files = []
        for pending_file in conv['pending_attachments']:
            attached_files.append({
                'name': pending_file['name'],
                'content': pending_file['content']
            })
        conv['pending_attachments'] = []
        save_conversations(conversations)

    # Handle regeneration
    if regenerate and regenerate_from is not None:
        msg_key = str(regenerate_from)

        if msg_key not in conv['versions']:
            conv['versions'][msg_key] = []
        
        if 'version_branches' not in conv:
            conv['version_branches'] = {}

        if regenerate_from < len(conv['messages']):
            current_response = conv['messages'][regenerate_from]['content']
            current_version_idx = conv['current_version_index'].get(msg_key, 0)
            
            if current_response not in conv['versions'][msg_key]:
                conv['versions'][msg_key].append(current_response)
                conv['current_version_index'][msg_key] = len(conv['versions'][msg_key]) - 1
                current_version_idx = len(conv['versions'][msg_key]) - 1
            
            subsequent_messages = conv['messages'][regenerate_from + 1:]
            if subsequent_messages:
                version_branch_key = f"{msg_key}_v{current_version_idx}"
                conv['version_branches'][version_branch_key] = subsequent_messages

        if regenerate_from > 0 and regenerate_from - 1 < len(conv['messages']):
            conv['messages'] = conv['messages'][:regenerate_from]
            conv['branch_root'] = regenerate_from - 1
            
        new_version_idx = len(conv['versions'].get(msg_key, []))
        conv['current_version_index'][msg_key] = new_version_idx
            
        indices_to_remove = []
        for idx_key in list(conv.get('current_version_index', {}).keys()):
            try:
                if int(idx_key) >= regenerate_from:
                    indices_to_remove.append(idx_key)
            except ValueError:
                continue
        
        for idx_key in indices_to_remove:
            del conv['current_version_index'][idx_key]

    # Handle file attachments
    full_message = message
    ai_message = message
    display_message = message
    
    if attached_files:
        file_contexts = []
        file_names = []
        for file_info in attached_files:
            file_names.append(file_info['name'])
            file_contexts.append(f"\n\n--- BEGIN FILE: {file_info['name']} ---\n{file_info['content']}\n--- END FILE: {file_info['name']} ---\n")
        
        ai_message = message + ''.join(file_contexts)
        file_list = ", ".join(file_names)
        display_message = message + (f"\n\n📎 **Attached files:** {file_list}" if message else f"📎 **Attached files:** {file_list}")
        
        full_message = display_message
    else:
        ai_message = message
        full_message = message

    response_data = {
        'response': '',
        'code_execution': None,
        'conversation_id': conversation_id,
        'title': conv['title'],
        'versions': conv.get('versions', {}),
        'current_version_index': conv.get('current_version_index', {})
    }

    # Handle commands
    if full_message.lower().startswith('/search'):
        query = full_message[7:].strip()
        if not query:
            response_data['response'] = "Please provide a search query. Example: `/search artificial intelligence`"
        else:
            response_data['response'] = search_web(query)

    elif full_message.lower().startswith('/extract'):
        url = full_message[8:].strip()
        if not url:
            response_data['response'] = "Please provide a URL. Example: `/extract https://example.com`"
        else:
            response_data['response'] = extract_web_content(url)

    elif full_message.lower().startswith('/code'):
        code = full_message[5:].strip()
        if not code:
            response_data['response'] = "Please provide Python code. Example: `/code print('Hello World!')`"
        else:
            exec_result = execute_python_code(code)
            response_data['code_execution'] = exec_result
            if exec_result['success']:
                response_data['response'] = f"✅ **Code executed successfully!**\n\n```\n{exec_result['output']}\n```"
            else:
                response_data['response'] = f"❌ **Code execution failed!**\n\n```\n{exec_result['error']}\n```"

    elif full_message.lower().startswith('/generate') or full_message.lower().startswith('/image'):
        if full_message.lower().startswith('/generate'):
            image_prompt = full_message[9:].strip()
        else:
            image_prompt = full_message[6:].strip()
        
        if not image_prompt:
            response_data['response'] = "Please provide an image description. Example: `/generate a beautiful sunset over mountains`"
        else:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"ai_gen_{timestamp}.png"
                
                try:
                    image_path = image_generator.generate_huggingface(image_prompt, output_name=filename)
                except Exception as e:
                    print(f"Hugging Face generation failed: {e}")
                    raise e
                
                image_filename = os.path.basename(image_path)
                
                image_html = f'''
<div style="text-align: center; margin: 15px 0;">
    <img src="/api/generated_image/{image_filename}" 
         alt="Generated: {image_prompt}" 
         style="max-width: 100%; max-height: 400px; border-radius: 12px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.3);"
         onclick="window.open('/api/generated_image/{image_filename}', '_blank')">
    <div style="margin-top: 8px; font-size: 0.75rem; color: var(--text-muted);">
        <i class="fas fa-expand"></i> Click to view full size
    </div>
</div>
'''
                response_data['response'] = f"🎨 **Generated Image: \"{image_prompt}\"**\n\n{image_html}"
                response_data['is_image_generation'] = True
                response_data['image_path'] = image_path
                response_data['image_prompt'] = image_prompt
                
            except Exception as e:
                print(f"Image generation error: {e}")
                response_data['response'] = f"❌ **Image generation failed!**\n\nError: {str(e)}\n\nPlease try a different prompt."

    elif full_message.lower().startswith('/help'):
        response_data['response'] = """**📚 HenAi Commands & Features**

**Commands:**
• `/search <query>` - Search the web
• `/extract <url>` - Extract content from a URL
• `/code <python>` - Execute Python code
• `/generate <description>` or `/image <description>` - Generate AI images (free!)
• `/help` - Show this help

**Features:**
• 📎 File attachments (text, code, images, archives)
• 💾 Auto-save conversations
• 🏷️ Auto-titled chats
• ✏️ Rename chats
• 🔄 Version history with branching
• 🎨 Free AI Image Generation
• 🔍 Unified File Search (Zenodo, GitHub, HuggingFace)"""
    
    elif is_image_generation_request(full_message) and not attached_files:
        image_prompt = extract_image_prompt(full_message)
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ai_gen_{timestamp}.png"
            
            try:
                image_path = image_generator.generate_huggingface(image_prompt, output_name=filename)
            except Exception as e:
                print(f"Hugging Face generation failed: {e}")
                raise e
            
            image_filename = os.path.basename(image_path)
            
            image_html = f'''
<div style="text-align: center; margin: 15px 0;">
    <img src="/api/generated_image/{image_filename}" 
         alt="Generated: {image_prompt}" 
         style="max-width: 100%; max-height: 400px; border-radius: 12px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.3);"
         onclick="window.open('/api/generated_image/{image_filename}', '_blank')">
    <div style="margin-top: 8px; font-size: 0.75rem; color: var(--text-muted);">
        <i class="fas fa-expand"></i> Click to view full size
    </div>
</div>
'''
            response_data['response'] = f"🎨 **Here's an image I generated for you:**\n\n{image_html}"
            response_data['is_image_generation'] = True
            response_data['image_path'] = image_path
            response_data['image_prompt'] = image_prompt
            
        except Exception as e:
            print(f"Image generation error: {e}")
            response_data['response'] = f"❌ **Image generation failed!**\n\nError: {str(e)}\n\nPlease try a different prompt."

    else:
        context = []
        for msg in conv['messages']:
            if msg['role'] == 'user' and msg.get('attachments'):
                if 'ai_content' in msg:
                    context.append({"role": msg['role'], "content": msg['ai_content']})
                else:
                    user_content = msg['content']
                    if 'attachments' in msg and msg['attachments']:
                        file_context = ""
                        for file_info in msg['attachments']:
                            if 'content' in file_info:
                                file_context += file_info['content']
                        if file_context:
                            user_content = msg['content'] + file_context
                    context.append({"role": msg['role'], "content": user_content})
            else:
                context.append({"role": msg['role'], "content": msg['content']})

        is_code_gen = is_code_generation_request(full_message)
        
        prompt_for_ai = ai_message if 'ai_message' in locals() else full_message
        
        if is_code_gen:
            prompt_for_ai += "\n\nIMPORTANT: Provide the COMPLETE, FULLY FUNCTIONAL code. Do not abbreviate or use placeholders."

        ai_response = query_ai_with_fallback(prompt_for_ai, context, is_code_gen)
        response_data['response'] = ai_response

    # Add messages
    if not regenerate or regenerate_from is None:
        stored_content = display_message if 'display_message' in locals() else full_message
        ai_ready_content = ai_message if 'ai_message' in locals() else full_message
        
        conv['messages'].append({
            'role': 'user',
            'content': stored_content,
            'ai_content': ai_ready_content,
            'timestamp': datetime.now().isoformat(),
            'attachments': attached_files if attached_files else None
        })
        conv['branch_root'] = None

    new_assistant_index = len(conv['messages'])
    conv['messages'].append({
        'role': 'assistant',
        'content': response_data['response'],
        'timestamp': datetime.now().isoformat()
    })

    if regenerate and regenerate_from is not None:
        msg_key = str(regenerate_from)
        if msg_key not in conv['versions']:
            conv['versions'][msg_key] = []

        if response_data['response'] not in conv['versions'][msg_key]:
            conv['versions'][msg_key].append(response_data['response'])
            conv['current_version_index'][msg_key] = len(conv['versions'][msg_key]) - 1

    if conv['title'] == 'New Chat':
        raw_title = generate_chat_title(conv['messages'])
        conv['title'] = sanitize_filename(raw_title)
        response_data['title'] = conv['title']

    conv['last_updated'] = datetime.now().isoformat()
    save_conversations(conversations)

    return jsonify(response_data)

@app.route('/api/edit_message', methods=['POST'])
def edit_message():
    data = request.json
    conversation_id = data.get('conversation_id')
    message_index = data.get('message_index')
    new_content = data.get('new_content')
    attached_files = data.get('attached_files', [])

    if conversation_id not in conversations:
        return jsonify({'error': 'Conversation not found'}), 404

    conv = conversations[conversation_id]

    if 'versions' not in conv:
        conv['versions'] = {}
    if 'current_version_index' not in conv:
        conv['current_version_index'] = {}

    messages = conv['messages']

    if message_index >= len(messages):
        return jsonify({'error': 'Message not found'}), 404

    full_content = new_content
    if attached_files:
        file_names = [file_info['name'] for file_info in attached_files]
        file_list = ", ".join(file_names)
        full_content = new_content + f"\n\n[Attached files: {file_list}]"

    if message_index + 1 < len(messages):
        msg_key = str(message_index + 1)
        if msg_key not in conv['versions']:
            conv['versions'][msg_key] = []
        
        if 'version_branches' not in conv:
            conv['version_branches'] = {}

        old_response = messages[message_index + 1]['content']
        current_version_idx = conv['current_version_index'].get(msg_key, 0)
        
        if old_response not in conv['versions'][msg_key]:
            conv['versions'][msg_key].append(old_response)
            conv['current_version_index'][msg_key] = len(conv['versions'][msg_key]) - 1
            current_version_idx = len(conv['versions'][msg_key]) - 1
        
        subsequent_messages = messages[message_index + 2:]
        if subsequent_messages:
            version_branch_key = f"{msg_key}_v{current_version_idx}"
            conv['version_branches'][version_branch_key] = subsequent_messages

    ai_ready_content = new_content
    if attached_files:
        file_context = ""
        for file_info in attached_files:
            if 'content' in file_info:
                file_context += file_info['content']
        if file_context:
            ai_ready_content = new_content + file_context
    
    messages[message_index]['content'] = full_content
    messages[message_index]['ai_content'] = ai_ready_content
    messages[message_index]['attachments'] = attached_files if attached_files else None

    while len(messages) > message_index + 1:
        messages.pop()

    context = []
    for msg in messages:
        if msg['role'] == 'user' and 'ai_content' in msg:
            context.append({"role": msg['role'], "content": msg['ai_content']})
        else:
            context.append({"role": msg['role'], "content": msg['content']})

    is_code_gen = is_code_generation_request(full_content)
    
    if is_code_gen:
        if not any(phrase in full_content.lower() for phrase in ['summarize', 'explain', 'what is', 'tell me about']):
            full_content += "\n\nIMPORTANT: Provide the COMPLETE, FULLY FUNCTIONAL code. Do not abbreviate or use placeholders."
    
    ai_response = query_ai_with_fallback(full_content, context, is_code_gen)

    messages.append({
        'role': 'assistant',
        'content': ai_response,
        'timestamp': datetime.now().isoformat()
    })

    msg_key = str(message_index + 1)
    if msg_key not in conv['versions']:
        conv['versions'][msg_key] = []

    if ai_response not in conv['versions'][msg_key]:
        conv['versions'][msg_key].append(ai_response)
        conv['current_version_index'][msg_key] = len(conv['versions'][msg_key]) - 1

    if conv['title'] == 'New Chat':
        conv['title'] = generate_chat_title(messages)

    conv['last_updated'] = datetime.now().isoformat()
    save_conversations(conversations)

    return jsonify({
        'success': True,
        'new_response': ai_response,
        'conversation_id': conversation_id,
        'messages': messages,
        'versions': conv.get('versions', {}),
        'current_version_index': conv.get('current_version_index', {})
    })

@app.route('/api/switch_version', methods=['POST'])
def switch_version():
    data = request.json
    conversation_id = data.get('conversation_id')
    message_index = data.get('message_index')
    version_index = data.get('version_index')

    if conversation_id not in conversations:
        return jsonify({'error': 'Conversation not found'}), 404

    conv = conversations[conversation_id]
    versions = conv.get('versions', {})
    msg_key = str(message_index)

    if msg_key not in versions or version_index >= len(versions[msg_key]):
        return jsonify({'error': 'Version not found'}), 404

    if 'current_version_index' not in conv:
        conv['current_version_index'] = {}
    
    previous_version_index = conv['current_version_index'].get(msg_key)
    conv['current_version_index'][msg_key] = version_index

    base_messages = conv['messages'][:message_index]
    version_response = versions[msg_key][version_index]
    
    version_branch_key = f"{msg_key}_v{version_index}"
    branch_messages = conv.get('version_branches', {}).get(version_branch_key, [])
    
    new_messages = list(base_messages)
    
    if message_index < len(conv['messages']):
        assistant_msg = dict(conv['messages'][message_index])
        assistant_msg['content'] = version_response
        new_messages.append(assistant_msg)
    
    if branch_messages:
        new_messages.extend(branch_messages)
    elif version_index == previous_version_index:
        subsequent = conv['messages'][message_index + 1:]
        if 'version_branches' not in conv:
            conv['version_branches'] = {}
        conv['version_branches'][version_branch_key] = list(subsequent)
        new_messages.extend(subsequent)
    
    conv['messages'] = new_messages
    conv['branch_root'] = message_index
    conv['branch_version'] = version_index

    save_conversations(conversations)

    return jsonify({
        'success': True,
        'content': version_response,
        'current_version_index': conv['current_version_index'],
        'messages': conv['messages']
    })

@app.route('/api/rename_chat', methods=['POST'])
def rename_chat():
    data = request.json
    conversation_id = data.get('conversation_id')
    new_title = data.get('new_title')

    if conversation_id not in conversations:
        return jsonify({'error': 'Conversation not found'}), 404

    conversations[conversation_id]['title'] = sanitize_filename(new_title)
    save_conversations(conversations)

    return jsonify({'success': True})

@app.route('/api/get_version', methods=['POST'])
def get_version():
    data = request.json
    conversation_id = data.get('conversation_id')
    message_index = data.get('message_index')
    version_index = data.get('version_index')

    if conversation_id not in conversations:
        return jsonify({'error': 'Conversation not found'}), 404

    conv = conversations[conversation_id]
    versions = conv.get('versions', {})
    msg_key = str(message_index)

    if msg_key not in versions or version_index >= len(versions[msg_key]):
        return jsonify({'error': 'Version not found'}), 404

    return jsonify({
        'success': True,
        'content': versions[msg_key][version_index]
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    filename = secure_filename(file.filename)
    file_content = file.read()

    try:
        text_content = extract_text_from_file(file_content, filename)
        
        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'txt'
        formatted_content = f"\n\n--- FILE: {filename} ({file_extension}) ---\n{text_content}\n--- END FILE: {filename} ---\n\n"

        return jsonify({
            'success': True,
            'filename': filename,
            'content': formatted_content,
            'preview': text_content[:500] + ('...' if len(text_content) > 500 else '')
        })
    except Exception as e:
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

@app.route('/api/add_pending_attachment', methods=['POST'])
def add_pending_attachment():
    data = request.json
    conversation_id = data.get('conversation_id')
    filename = data.get('filename')
    content = data.get('content')
    
    if not conversation_id or not filename:
        return jsonify({'error': 'Missing conversation_id or filename'}), 400
    
    if content:
        content = content.encode('utf-8', errors='replace').decode('utf-8')
    
    if conversation_id not in conversations:
        return jsonify({'error': 'Conversation not found'}), 404
    
    conv = conversations[conversation_id]
    
    if 'pending_attachments' not in conv:
        conv['pending_attachments'] = []
    
    conv['pending_attachments'].append({
        'name': filename,
        'content': content,
        'timestamp': datetime.now().isoformat(),
        'source': 'archive_search'
    })
    
    conv['last_updated'] = datetime.now().isoformat()
    
    try:
        save_conversations(conversations)
    except Exception as e:
        print(f"Error saving: {e}")
        return jsonify({'error': f'Failed to save attachment: {str(e)}'}), 500
    
    return jsonify({
        'success': True,
        'conversation_id': conversation_id,
        'filename': filename,
        'attachments_count': len(conv['pending_attachments'])
    })

@app.route('/api/attach_to_chat', methods=['POST'])
def attach_to_chat():
    data = request.json
    conversation_id = data.get('conversation_id')
    filename = data.get('filename')
    content = data.get('content')
    
    if not conversation_id or not filename:
        return jsonify({'error': 'Missing conversation_id or filename'}), 400
    
    if content:
        content = content.encode('utf-8', errors='replace').decode('utf-8')
    
    if conversation_id not in conversations:
        conversation_id = str(uuid.uuid4())
        conversations[conversation_id] = {
            'id': conversation_id,
            'messages': [],
            'title': 'New Chat',
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'versions': {},
            'current_version_index': {},
            'branch_root': None,
            'pending_attachments': []
        }
    
    conv = conversations[conversation_id]
    
    if 'pending_attachments' not in conv:
        conv['pending_attachments'] = []
    
    conv['pending_attachments'].append({
        'name': filename,
        'content': content,
        'timestamp': datetime.now().isoformat(),
        'source': 'archive_search'
    })
    
    conv['last_updated'] = datetime.now().isoformat()
    
    try:
        save_conversations(conversations)
    except Exception as e:
        print(f"Error saving: {e}")
        if 'pending_attachments' in conv and conv['pending_attachments']:
            conv['pending_attachments'].pop()
            save_conversations(conversations)
    
    return jsonify({
        'success': True,
        'conversation_id': conversation_id,
        'filename': filename,
        'attachments_count': len(conv['pending_attachments'])
    })

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    conv_list = []
    for conv_id, conv_data in conversations.items():
        conv_list.append({
            'id': conv_id,
            'title': conv_data.get('title', 'New Chat'),
            'message_count': len(conv_data.get('messages', [])),
            'last_updated': conv_data.get('last_updated', datetime.now().isoformat())
        })
    conv_list.sort(key=lambda x: x['last_updated'], reverse=True)
    return jsonify(conv_list)

@app.route('/api/conversation/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    if conversation_id in conversations:
        conv_data = conversations[conversation_id]
        
        messages = conv_data.get('messages', [])
        for msg in messages:
            if msg.get('media_data'):
                msg['media_data'] = msg['media_data']
        
        return jsonify({
            **conv_data,
            'versions': conv_data.get('versions', {}),
            'current_version_index': conv_data.get('current_version_index', {}),
            'version_branches': conv_data.get('version_branches', {}),
            'branch_root': conv_data.get('branch_root'),
            'branch_version': conv_data.get('branch_version'),
            'pending_attachments': conv_data.get('pending_attachments', [])
        })
    return jsonify({'error': 'Conversation not found'}), 404

@app.route('/api/delete_conversation/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    if conversation_id in conversations:
        del conversations[conversation_id]
        save_conversations(conversations)
        return jsonify({'success': True})
    return jsonify({'error': 'Conversation not found'}), 404

@app.route('/api/remove_pending_attachment', methods=['POST'])
def remove_pending_attachment():
    data = request.json
    conversation_id = data.get('conversation_id')
    attachment_index = data.get('attachment_index')
    
    if conversation_id not in conversations:
        return jsonify({'error': 'Conversation not found'}), 404
    
    conv = conversations[conversation_id]
    
    if 'pending_attachments' not in conv:
        return jsonify({'error': 'No pending attachments'}), 404
    
    if attachment_index >= len(conv['pending_attachments']):
        return jsonify({'error': 'Attachment not found'}), 404
    
    conv['pending_attachments'].pop(attachment_index)
    
    if len(conv['pending_attachments']) == 0:
        conv['pending_attachments'] = []
    
    conv['last_updated'] = datetime.now().isoformat()
    save_conversations(conversations)
    
    return jsonify({'success': True, 'remaining': len(conv['pending_attachments'])})

@app.route('/api/clear_pending_attachments', methods=['POST'])
def clear_pending_attachments():
    data = request.json
    conversation_id = data.get('conversation_id')
    
    if conversation_id not in conversations:
        return jsonify({'error': 'Conversation not found'}), 404
    
    conv = conversations[conversation_id]
    conv['pending_attachments'] = []
    conv['last_updated'] = datetime.now().isoformat()
    save_conversations(conversations)
    
    return jsonify({'success': True})

# ============= MEDIA API ENDPOINTS =============

@app.route('/api/media/search/image', methods=['POST'])
def search_image():
    data = request.json
    query = data.get('query', '').strip()
    provider = data.get('provider')
    
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    if provider:
        result = media_handler.search_images(query, provider)
    else:
        result = media_handler.search_with_fallback(query, 'image')
    
    return jsonify(result)

@app.route('/api/media/search/video', methods=['POST'])
def search_video():
    data = request.json
    query = data.get('query', '').strip()
    provider = data.get('provider')
    
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    if provider:
        result = media_handler.search_videos(query, provider)
    else:
        result = media_handler.search_with_fallback(query, 'video')
    
    return jsonify(result)

@app.route('/api/media/regenerate', methods=['POST'])
def regenerate_media():
    data = request.json
    query = data.get('query', '').strip()
    media_type = data.get('media_type', 'image')
    current_id = data.get('current_id')
    provider = data.get('provider')
    
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    result = media_handler.regenerate_with_fallback(query, media_type, current_id, provider)
    
    return jsonify(result)

@app.route('/api/media/analyze/video', methods=['POST'])
def analyze_video():
    data = request.json
    video_url = data.get('video_url', '')
    video_name = data.get('video_name', 'video.mp4')
    
    if not video_url:
        return jsonify({'error': 'No video URL provided'}), 400
    
    result = media_handler.analyze_video(video_url, video_name)
    return jsonify(result)

@app.route('/api/media/analyze/image', methods=['POST'])
def analyze_image():
    data = request.json
    image_url = data.get('image_url', '')
    image_name = data.get('image_name', 'image.jpg')
    
    if not image_url:
        return jsonify({'error': 'No image URL provided'}), 400
    
    temp_file_path = None
    try:
        print(f"📥 Downloading image from: {image_url}")
        response = requests.get(image_url, timeout=30, stream=True)
        response.raise_for_status()
        
        image_content = response.content
        
        import tempfile
        import re
        
        ext = image_name.split('.')[-1].lower() if '.' in image_name else 'jpg'
        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
            ext = 'jpg'
        
        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
            tmp.write(image_content)
            tmp.flush()
            temp_file_path = tmp.name
        
        print(f"📁 Image saved to temp file: {temp_file_path}")
        
        from vision import get_vision_model
        vision_model = get_vision_model()
        
        print("🔍 Analyzing image content with Vision Model...")
        vision_analysis = vision_model.analyze_image(image_content)
        
        clean_analysis = ""
        
        if vision_analysis and len(vision_analysis) > 10:
            clean_analysis = vision_analysis
            print(f"✅ Using Vision Model analysis ({len(clean_analysis)} chars)")
        else:
            name_without_ext = re.sub(r'\.[^.]+$', '', image_name)
            clean_name = re.sub(r'[_\-\.]', ' ', name_without_ext)
            clean_name = re.sub(r'\d+', '', clean_name).strip()
            if clean_name and len(clean_name) > 3:
                clean_analysis = f"This image appears to show {clean_name}."
            else:
                clean_analysis = "The image has been processed, but no readable text or recognizable content was detected."
            print("⚠️ Using filename fallback")
        
        metadata_patterns = [
            r'Photographer:?\s*\S+',
            r'Photo by\s+\S+',
            r'Credit:?\s*\S+',
            r'Source:?\s*\S+',
            r'Copyright\s+[©]?\s*\S+',
            r'©\s*\d{4}\s*\S+',
            r'\[.*?\]',
            r'\(.*?(credit|courtesy|source).*?\)',
            r'Image courtesy of\s+\S+',
            r'Sourced from\s+\S+',
            r'^\w+:\s*$',
            r'\*\*Image Analysis:.*?\*\*',
            r'\*\*AI Analysis:\*\*',
            r'\*\*OCR Extracted Text Found:\*\*',
            r'\*\*Note:\*\*',
            r'\*\*Image Details:\*\*',
            r'\*\*Final Analysis:\*\*',
            r'---.*?---',
        ]
        
        for pattern in metadata_patterns:
            clean_analysis = re.sub(pattern, '', clean_analysis, flags=re.IGNORECASE | re.MULTILINE)
        
        clean_analysis = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean_analysis)
        clean_analysis = re.sub(r'`([^`]+)`', r'\1', clean_analysis)
        clean_analysis = re.sub(r'#+\s*', '', clean_analysis)
        clean_analysis = re.sub(r'\s+', ' ', clean_analysis)
        clean_analysis = re.sub(r'\n{3,}', '\n\n', clean_analysis)
        
        if clean_analysis and len(clean_analysis) > 0:
            clean_analysis = clean_analysis[0].upper() + clean_analysis[1:] if len(clean_analysis) > 1 else clean_analysis.upper()
        
        clean_analysis = re.sub(r'\s*[|;:]\s*$', '', clean_analysis)
        clean_analysis = clean_analysis.strip()
        
        if not clean_analysis or len(clean_analysis) < 5:
            clean_analysis = "The image has been analyzed, but no specific content could be identified."
        
        response_data = {
            'success': True,
            'image_url': image_url,
            'image_name': image_name,
            'analysis': clean_analysis
        }
        
        print(f"✅ Analysis complete: {clean_analysis[:100]}...")
        return jsonify(response_data)
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to download image: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to download image: {str(e)}'
        }), 500
    except Exception as e:
        print(f"❌ Error analyzing image: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Error analyzing image: {str(e)}'
        }), 500
    finally:
        if temp_file_path:
            try:
                import os
                os.unlink(temp_file_path)
            except:
                pass

@app.route('/api/save_media_message', methods=['POST'])
def save_media_message():
    data = request.json
    conversation_id = data.get('conversation_id')
    user_message = data.get('user_message', '')
    assistant_response = data.get('assistant_response', '')
    media_data = data.get('media_data')
    is_error = data.get('is_error', False)
    
    if not conversation_id or conversation_id not in conversations:
        conversation_id = str(uuid.uuid4())
        conversations[conversation_id] = {
            'id': conversation_id,
            'messages': [],
            'title': 'New Chat',
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'versions': {},
            'current_version_index': {},
            'branch_root': None,
            'pending_attachments': []
        }
    
    conv = conversations[conversation_id]
    
    user_msg = {
        'role': 'user',
        'content': user_message,
        'timestamp': datetime.now().isoformat(),
        'attachments': None
    }
    conv['messages'].append(user_msg)
    
    assistant_msg = {
        'role': 'assistant',
        'content': assistant_response,
        'timestamp': datetime.now().isoformat(),
        'media_data': media_data,
        'is_media_result': True,
        'is_error': is_error
    }
    conv['messages'].append(assistant_msg)
    
    if conv['title'] == 'New Chat' and user_message:
        raw_title = generate_chat_title(conv['messages'])
        conv['title'] = sanitize_filename(raw_title)
    
    conv['last_updated'] = datetime.now().isoformat()
    save_conversations(conversations)
    
    return jsonify({
        'success': True,
        'conversation_id': conversation_id,
        'title': conv['title']
    })

# Register workspace routes
register_workspace_routes(app)

@app.route('/api/generated_image/<filename>')
def serve_generated_image(filename):
    from flask import send_from_directory
    
    if '..' in filename or filename.startswith('/'):
        return jsonify({'error': 'Invalid filename'}), 400
    
    image_dir = os.path.join(os.path.dirname(__file__), 'generated_images')
    return send_from_directory(image_dir, filename)

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🐔 HenAi Server Started! (Chat & Search Mode)")
    print("="*60)
    print("📍 Visit: http://localhost:5000")
    print("🤖 AI Mode: Hybrid - Pollinations.ai for conversations, OpenRouter for code")
    print("🖼️ Media Search: Images & Videos from Pixabay and Pexels")
    print("🎬 Video Analysis: TwelveLabs API")
    print("💡 Commands: /search, /extract, /code, /image, /help")
    print("📋 Features: Copy, Edit, Regenerate, Version Toggle, Rename")
    print("📎 File Support: Text, Code, Images, Archives")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5001)
