# app.py - Complete backend for Chat, Documents, and Search Files modes
# Includes all imports from models.py, docs.py, workspace.py, etc.

import os
import json
import re
import uuid
from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import requests
from datetime import datetime
from io import BytesIO
from docx import Document
from docx.shared import Inches
import base64
import io
import pandas as pd
from PIL import Image

# ============= IMPORT AI FUNCTIONS FROM models.py =============
from models import (
    query_ai_with_fallback,
    generate_chat_title,
    is_code_generation_request,
    execute_python_code,
    search_web,
    extract_web_content,
    analyze_image_with_ai,
    call_pollinations_ai,
    query_openrouter
)

# ============= IMPORT DOCUMENT PROCESSING FROM docs.py =============
from docs import DocumentProcessor

# ============= IMPORT WORKSPACE FUNCTIONS FROM workspace.py =============
from workspace import (
    register_workspace_routes,
    load_workspace,
    save_workspace,
    build_folder_context,
    get_file_content_from_workspace
)

# ============= IMPORT DOCUMENT CREATOR FROM mydocs.py =============
from mydocs import DocumentCreator

# ============= IMPORT VISION MODEL FROM vision.py =============
from vision import get_vision_model

# ============= IMPORT BINARY PROCESSOR =============
from binary_processor import BinaryProcessor

# ============= IMPORT MEDIA HANDLER =============
from media import media_handler

# ============= IMPORT TERMINAL BLUEPRINT =============
from terminal import create_terminal_blueprint

# ============= IMPORT FREE IMAGE GENERATOR =============
from image import FreeImageGenerator

# ============= INITIALIZE FLASK APP =============
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
CORS(app)

# ============= REGISTER BLUEPRINTS =============
app.register_blueprint(create_terminal_blueprint(app))

# ============= INITIALIZE COMPONENTS =============
binary_processor = BinaryProcessor()
image_generator = FreeImageGenerator(output_dir="generated_images")
doc_processor = DocumentProcessor()
doc_creator = DocumentCreator()

# ============= ENSURE DIRECTORIES EXIST =============
os.makedirs('generated_images', exist_ok=True)

# ============= CONVERSATIONS STORAGE =============
CONVERSATIONS_FILE = 'conversations.json'

ALLOWED_EXTENSIONS = {
    'txt', 'md', 'py', 'js', 'html', 'css', 'json', 'xml', 'csv',
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'zip', 'rar', '7z'
}

def sanitize_filename(text):
    """Sanitize text to be safe for use in filenames"""
    if not text:
        return "New Chat"
    text = ''.join(char for char in text if char.isprintable() and char not in '\n\r\t')
    replacements = {'/': '-', '\\': '-', ':': '-', '*': '-', '?': '-', '"': "'", '<': '-', '>': '-', '|': '-'}
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
                    if 'pending_attachments' not in conv_data:
                        conv_data['pending_attachments'] = []
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
    """Extract text from uploaded files using binary processor"""
    try:
        processed_output = binary_processor.process_file(file_content, filename)
        if len(processed_output) > 50000:
            processed_output = processed_output[:50000] + "\n\n[Content truncated due to size]"
        return processed_output
    except Exception as e:
        print(f"Error in extraction: {e}")
        return f"[Error extracting from {filename}: {str(e)}]"

def export_to_word(conversation_data):
    """Export conversation to Word document"""
    doc = Document()
    doc.add_heading(f'HenAi Chat: {conversation_data["title"]}', 0)
    doc.add_paragraph(f'Exported on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    doc.add_paragraph('-' * 50)

    for msg in conversation_data['messages']:
        if msg['role'] == 'user':
            doc.add_heading('You:', level=2)
        else:
            doc.add_heading('HenAi:', level=2)

        code_blocks = re.findall(r'```(\w+)?\n([\s\S]*?)```', msg['content'])
        if code_blocks:
            parts = re.split(r'```\w*\n[\s\S]*?```', msg['content'])
            for i, part in enumerate(parts):
                if part.strip():
                    doc.add_paragraph(part.strip())
                if i < len(code_blocks):
                    lang, code = code_blocks[i]
                    doc.add_paragraph(f'[{lang.upper()} Code]')
                    doc.add_paragraph(code.strip())
        else:
            doc.add_paragraph(msg['content'])
        doc.add_paragraph('')

    return doc

# ============= ROUTES =============

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
            'branch_root': None,
            'pending_attachments': []
        }

    conv = conversations[conversation_id]

    if 'versions' not in conv:
        conv['versions'] = {}
    if 'current_version_index' not in conv:
        conv['current_version_index'] = {}
    if 'branch_root' not in conv:
        conv['branch_root'] = None

    # Handle pending attachments from archive search
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
            response_data['response'] = "Please provide an image description. Example: `/generate a beautiful sunset`"
        else:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"ai_gen_{timestamp}.png"
                
                try:
                    image_path = image_generator.generate_huggingface(image_prompt, output_name=filename)
                except Exception as e:
                    print(f"Hugging Face failed: {e}")
                    try:
                        image_path = image_generator.generate_local_sd(image_prompt, output_name=filename)
                    except Exception as e2:
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
                response_data['response'] = f"❌ **Image generation failed!**\n\nError: {str(e)}"

    elif full_message.lower().startswith('/help'):
        response_data['response'] = """**📚 HenAi Commands & Features**

**Commands:**
• `/search <query>` - Search the web
• `/extract <url>` - Extract content from a URL
• `/code <python>` - Execute Python code
• `/generate <description>` - Generate AI images
• `/help` - Show this help

**Chat Features:**
• 📋 Copy messages
• ✏️ Edit your messages
• 🔄 Regenerate responses
• ↔️ Toggle between version branches
• 📎 File attachments (text, code, documents)
• 💾 Auto-save conversations
• 📥 Export chats to Word

**Documents Mode:**
• Create Word, PDF, Excel, PowerPoint documents
• Extract text from documents
• Merge/Split PDFs
• Convert between formats

**Search Files Mode:**
• Search Zenodo for research papers
• Search GitHub for repositories
• Download and attach files to chat"""

    else:
        # Build context from conversation history
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
        prompt_for_ai = ai_message
        
        if is_code_gen:
            prompt_for_ai += "\n\nIMPORTANT: Provide the COMPLETE, FULLY FUNCTIONAL code with at least 500 lines. Do not abbreviate or use placeholders."

        ai_response = query_ai_with_fallback(prompt_for_ai, context, is_code_gen)
        response_data['response'] = ai_response

    # Add messages to conversation
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
            full_content += "\n\nIMPORTANT: Provide the COMPLETE, FULLY FUNCTIONAL code with at least 500 lines."
    
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

@app.route('/api/export_chat/<conversation_id>', methods=['GET'])
def export_chat(conversation_id):
    if conversation_id not in conversations:
        return jsonify({'error': 'Conversation not found'}), 404

    doc = export_to_word(conversations[conversation_id])

    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    title = conversations[conversation_id]['title']
    title = ''.join(char for char in title if char.isprintable() and char not in '\n\r\t')
    title = title.replace('/', '-').replace('\\', '-').replace(':', '-')
    
    filename = f"HenAi_Chat_{title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

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
    save_conversations(conversations)
    
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

# ============= DOCS API ENDPOINTS =============

@app.route('/api/docs/generate', methods=['POST'])
def docs_generate():
    """Generate document content using AI"""
    data = request.json
    prompt = data.get('prompt', '')
    doc_type = data.get('doc_type', 'word')
    template_id = data.get('template_id')
    
    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400
    
    enhanced_prompt = doc_creator._apply_template_formatting(prompt, doc_type, template_id) if template_id else prompt
    
    try:
        from models import query_openrouter
        response = query_openrouter(enhanced_prompt, context=None, is_code_generation=False)
        
        if response:
            return jsonify({'success': True, 'content': response})
        else:
            return jsonify({'error': 'AI generation failed'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/docs/create', methods=['POST'])
def docs_create():
    """Create a document from generated content"""
    data = request.json
    doc_type = data.get('doc_type', 'word')
    content = data.get('content', '')
    filename = data.get('filename', 'document')
    template_id = data.get('template_id')
    
    if not content:
        return jsonify({'error': 'No content provided'}), 400
    
    try:
        output_path = doc_creator.create_document(content, doc_type, filename, template_id)
        
        if output_path and output_path.exists():
            download_url = f'/api/docs/download/{output_path.name}'
            return jsonify({
                'success': True,
                'filename': output_path.name,
                'download_url': download_url
            })
        else:
            return jsonify({'error': 'Failed to create document'}), 500
    except Exception as e:
        print(f"Error creating document: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/docs/download/<filename>', methods=['GET'])
def docs_download(filename):
    file_path = doc_creator.output_dir / filename
    if file_path.exists():
        return send_file(file_path, as_attachment=True, download_name=filename)
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/docs/extract', methods=['POST'])
def docs_extract():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    extract_type = request.form.get('extract_type', 'text')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    filename = secure_filename(file.filename)
    file_content = file.read()
    
    try:
        temp_path = doc_creator.temp_dir / filename
        with open(temp_path, 'wb') as f:
            f.write(file_content)
        
        extracted_content = ""
        suffix = os.path.splitext(filename)[1].lower()
        
        if suffix in ['.docx', '.doc']:
            result = doc_processor.read_word_document(str(temp_path))
            extracted_content = '\n'.join(result['paragraphs'])
        elif suffix == '.pdf':
            result = doc_processor.read_pdf(str(temp_path), extract_tables=False)
            extracted_content = '\n'.join([page['text'] for page in result['pages']])
        elif suffix in ['.pptx', '.ppt']:
            result = doc_processor.read_presentation(str(temp_path))
            for slide in result['slides']:
                extracted_content += slide['text_content'] + '\n'
        elif suffix in ['.xlsx', '.xls', '.csv']:
            if suffix == '.csv':
                df = pd.read_csv(str(temp_path))
            else:
                df = pd.read_excel(str(temp_path))
            extracted_content = df.to_string()
        elif suffix in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            extracted_content = doc_processor.extract_text_from_image(str(temp_path))
        else:
            extracted_content = doc_processor.extract_text_from_file(str(temp_path))
        
        return jsonify({'success': True, 'content': extracted_content[:50000], 'filename': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

@app.route('/api/docs/merge', methods=['POST'])
def docs_merge():
    files = request.files.getlist('files')
    output_name = request.form.get('output_name', 'merged_document')
    
    if len(files) < 2:
        return jsonify({'error': 'Need at least 2 files to merge'}), 400
    
    try:
        temp_files = []
        for file in files:
            if file.filename and file.filename.lower().endswith('.pdf'):
                temp_path = doc_creator.temp_dir / secure_filename(file.filename)
                file.save(str(temp_path))
                temp_files.append(str(temp_path))
        
        output_filename = f"{output_name}.pdf"
        result_path = doc_processor.merge_pdfs(temp_files, output_filename)
        
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
        
        download_url = f'/api/docs/download/{output_filename}'
        return jsonify({'success': True, 'filename': output_filename, 'download_url': download_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/docs/split', methods=['POST'])
def docs_split():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    pages_per_file = int(request.form.get('pages_per_file', 1))
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'File must be PDF'}), 400
    
    try:
        temp_path = doc_creator.temp_dir / secure_filename(file.filename)
        file.save(str(temp_path))
        
        split_dir = doc_creator.temp_dir / 'split_output'
        split_files = doc_processor.split_pdf(str(temp_path), str(split_dir), pages_per_file)
        
        result_files = []
        for split_file in split_files:
            filename = os.path.basename(split_file)
            result_files.append({'name': filename, 'url': f'/api/docs/download/{filename}'})
            import shutil
            shutil.move(split_file, str(doc_creator.output_dir / filename))
        
        os.unlink(temp_path)
        
        return jsonify({'success': True, 'files_count': len(result_files), 'files': result_files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/docs/convert', methods=['POST'])
def docs_convert():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    to_format = request.form.get('to_format', 'txt')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    filename = secure_filename(file.filename)
    file_content = file.read()
    
    try:
        temp_path = doc_creator.temp_dir / filename
        with open(temp_path, 'wb') as f:
            f.write(file_content)
        
        ext_map = {'txt': '.txt', 'docx': '.docx', 'pdf': '.pdf', 'xlsx': '.xlsx', 'csv': '.csv', 'html': '.html'}
        output_ext = ext_map.get(to_format, '.txt')
        output_filename = f"{os.path.splitext(filename)[0]}{output_ext}"
        
        output_path = doc_processor.convert_document(str(temp_path), output_filename, output_format=to_format)
        
        os.unlink(temp_path)
        
        download_url = f'/api/docs/download/{os.path.basename(output_path)}'
        return jsonify({'success': True, 'filename': os.path.basename(output_path), 'format': to_format, 'download_url': download_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/docs/resize', methods=['POST'])
def docs_resize():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    width = request.form.get('width')
    height = request.form.get('height')
    maintain_aspect = request.form.get('maintain_aspect', 'true').lower() == 'true'
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    filename = secure_filename(file.filename)
    file_content = file.read()
    
    try:
        temp_path = doc_creator.temp_dir / filename
        with open(temp_path, 'wb') as f:
            f.write(file_content)
        
        w = int(width) if width else None
        h = int(height) if height else None
        output_filename = f"resized_{filename}"
        
        output_path = doc_processor.resize_image(str(temp_path), output_filename, width=w, height=h, maintain_aspect=maintain_aspect)
        
        from PIL import Image
        img = Image.open(output_path)
        new_width, new_height = img.size
        
        os.unlink(temp_path)
        
        download_url = f'/api/docs/download/{output_filename}'
        return jsonify({'success': True, 'filename': output_filename, 'width': new_width, 'height': new_height, 'download_url': download_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= MEDIA SEARCH ENDPOINTS =============

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

@app.route('/api/media/analyze/image', methods=['POST'])
def analyze_image():
    data = request.json
    image_url = data.get('image_url', '')
    image_name = data.get('image_name', 'image.jpg')
    
    if not image_url:
        return jsonify({'error': 'No image URL provided'}), 400
    
    temp_file_path = None
    try:
        response = requests.get(image_url, timeout=30, stream=True)
        response.raise_for_status()
        image_content = response.content
        
        ext = image_name.split('.')[-1].lower() if '.' in image_name else 'jpg'
        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
            ext = 'jpg'
        
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
            tmp.write(image_content)
            tmp.flush()
            temp_file_path = tmp.name
        
        from vision import get_vision_model
        vision_model = get_vision_model()
        vision_analysis = vision_model.analyze_image(image_content)
        
        clean_analysis = vision_analysis if vision_analysis and len(vision_analysis) > 10 else "The image has been processed but no specific content could be identified."
        
        return jsonify({'success': True, 'image_url': image_url, 'image_name': image_name, 'analysis': clean_analysis})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if temp_file_path:
            try:
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
    
    conv['messages'].append({'role': 'user', 'content': user_message, 'timestamp': datetime.now().isoformat(), 'attachments': None})
    conv['messages'].append({'role': 'assistant', 'content': assistant_response, 'timestamp': datetime.now().isoformat(), 'media_data': media_data, 'is_media_result': True, 'is_error': is_error})
    
    if conv['title'] == 'New Chat' and user_message:
        raw_title = generate_chat_title(conv['messages'])
        conv['title'] = sanitize_filename(raw_title)
    
    conv['last_updated'] = datetime.now().isoformat()
    save_conversations(conversations)
    
    return jsonify({'success': True, 'conversation_id': conversation_id, 'title': conv['title']})

# ============= GENERATED IMAGE SERVING =============

@app.route('/api/generated_image/<filename>')
def serve_generated_image(filename):
    from flask import send_from_directory
    if '..' in filename or filename.startswith('/'):
        return jsonify({'error': 'Invalid filename'}), 400
    image_dir = os.path.join(os.path.dirname(__file__), 'generated_images')
    return send_from_directory(image_dir, filename)

# ============= REGISTER WORKSPACE ROUTES =============
register_workspace_routes(app)

# ============= MAIN =============
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🐔 HenAi Server Started - Chat, Documents & Search Modes")
    print("="*60)
    print("📍 Visit: http://localhost:5000")
    print("💬 Chat Mode: AI conversations with file attachments, version branching")
    print("📄 Documents Mode: Create Word/PDF/Excel, Extract text, Merge/Split PDFs")
    print("🔍 Search Files Mode: Search Zenodo & GitHub archives")
    print("📋 Commands: /search, /extract, /code, /generate, /help")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5001)
