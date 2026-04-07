# models.py - AI Models and Functionality for HenAi

import os
import re
import requests
import tempfile
import subprocess
import sys
from flask import Response, jsonify
import json

# ============= AI CONFIGURATION =============

# OpenRouter API Key
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# ============= AI CORE FUNCTIONS =============

def get_available_models():
    """Fetch available free models from OpenRouter"""
    try:
        url = "https://openrouter.ai/api/v1/models"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            models_data = response.json()
            free_models = []
            for model in models_data.get('data', []):
                pricing = model.get('pricing', {})
                if pricing.get('prompt') == '0' or pricing.get('request') == '0':
                    free_models.append(model['id'])
            return free_models[:5]
    except Exception as e:
        print(f"Error fetching models: {e}")

    return [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "minimax/minimax-m2.5:free",
        "microsoft/phi-3.5-mini-128k-instruct:free",
        "stepfun/step-3.5-flash:free",
        "arcee-ai/trinity-large-preview:free",
        "google/gemini-2.0-flash-exp:free",  
        "openrouter/free"
    ]


def extract_code_from_response(response_text):
    """Extract only the code from the response, removing reasoning"""
    if not response_text:
        return response_text
    
    # Remove markdown code blocks if present
    code_match = re.search(r'```(?:html|css|javascript|js|python)?\n(.*?)```', response_text, re.DOTALL)
    if code_match:
        return code_match.group(1).strip()
    
    # Look for HTML starting with <!DOCTYPE
    html_match = re.search(r'<!DOCTYPE html>.*', response_text, re.DOTALL | re.IGNORECASE)
    if html_match:
        return html_match.group(0).strip()
    
    # Look for HTML starting with <html
    html_match = re.search(r'<html.*?>.*?</html>', response_text, re.DOTALL | re.IGNORECASE)
    if html_match:
        return html_match.group(0).strip()
    
    # If it contains HTML tags, return as is
    if re.search(r'<[a-z].*?>', response_text, re.IGNORECASE):
        return response_text
    
    # If it contains CSS
    if re.search(r'\{[^}]+\}', response_text) and re.search(r'[a-z-]+\s*:', response_text):
        return response_text
    
    # If it contains JavaScript
    if re.search(r'function\s*\(|const\s+|let\s+|var\s+|=>', response_text):
        return response_text
    
    # Remove any lines that look like reasoning
    lines = response_text.split('\n')
    filtered_lines = []
    in_code = False
    
    for line in lines:
        # Skip lines that are JSON objects
        if line.strip().startswith('{"role"'):
            continue
        # Skip lines that are reasoning indicators
        if 'reasoning_content' in line or '"tool_calls"' in line:
            continue
        # Skip lines that are just thinking phrases
        if not in_code and any(phrase in line.lower() for phrase in [
            'i will', 'let me', 'first,', 'we need', 'the code will',
            'here is', 'here\'s', 'below is', 'this will', 'we can',
            'i think', 'i should', 'i need to', 'the user', 'they want',
            'maybe', 'perhaps', 'let\'s', 'we should', 'we could'
        ]):
            continue
        # If we see code indicators, we're in code
        if re.search(r'<[a-z].*?>|function|const|let|var|{', line):
            in_code = True
            filtered_lines.append(line)
        elif in_code:
            filtered_lines.append(line)
    
    result = '\n'.join(filtered_lines).strip()
    
    # If we filtered everything out, return original
    if len(result) < 50:
        return response_text
    
    return result


def call_pollinations_ai(messages, stream=False):
    """Call Pollinations.ai API for NON-CODE requests only (conversations, explanations)"""
    try:
        # System prompt for personality
        system_msg = {
            "role": "system", 
            "content": """You are HenAi, an expert AI assistant created by NexusCraft. 
When asked about your name, identity, or creator, respond with: 
'My name is HenAi, I'm an AI assistant created by NexusCraft, and I'm glad to be helping you! 😊 
Is there anything else you'd like to know, or anything else I can assist with today?'

IMPORTANT RULES:
1. When answering questions, be concise and direct
2. Never include reasoning or thinking in your responses
3. Maintain context from the full conversation history
4. Be helpful, friendly, and engaging

Remember: Your response should be natural and conversational."""
        }
        
        url = "https://text.pollinations.ai/"
        
        # Prepare payload with ALL messages for context
        payload = {
            "messages": [system_msg] + messages,
            "model": "openai",
            "stream": stream,
            "temperature": 0.7,
            "max_tokens": 4000
        }
        
        if stream:
            response = requests.post(url, json=payload, stream=True, timeout=60)
            response.raise_for_status()
            
            def generate():
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        try:
                            text = line.decode('utf-8')
                            # Skip any JSON metadata lines
                            if not any(skip in text.lower() for skip in ['{"role"', 'reasoning', 'tool_calls']):
                                full_response += text
                                yield f"data: {json.dumps({'content': text})}\n\n"
                        except:
                            continue
                yield f"data: {json.dumps({'done': True})}\n\n"
            
            return Response(generate(), mimetype='text/event-stream')
        else:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            
            raw_response = response.text.strip()
            
            # Clean the response to remove reasoning
            cleaned_response = extract_code_from_response(raw_response)
            
            return cleaned_response
            
    except Exception as e:
        print(f"❌ Pollinations.ai error: {e}")
        return None


def query_openrouter(prompt, context=None, is_code_generation=False):
    """Query OpenRouter with full context - USED FOR ALL CODE GENERATION"""
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "HenAi"
        }

        messages = []

        # Enhanced system prompt based on request type
        is_title_gen = prompt.startswith("Based on this conversation, generate a very short title")
        
        if is_code_generation:
            system_prompt = """You are an expert AI coding assistant named HenAi created by NexusCraft.

CRITICAL RULES FOR CODE GENERATION:
1. ALWAYS provide COMPLETE, FULLY FUNCTIONAL code - never abbreviate or use placeholders like "// rest of code" or "..."
2. Generate AT LEAST 500 lines of code for any substantial project
3. Include ALL necessary components: imports, functions, classes, error handling, and comments
4. For HTML/CSS/JS projects, create complete, production-ready code with proper styling
5. Use modern best practices and design patterns
6. Include comprehensive comments explaining key sections
7. Ensure the code is immediately runnable/usable without modifications
8. If generating a web app, include responsive design, proper meta tags, and complete styling
9. If asked your name say you are HenAi Assistant created by NexusCraft

Your code should be enterprise-grade, well-structured, and ready for production use."""
        elif is_title_gen:
            system_prompt = "You are a title generator. Generate ONLY the title, maximum 5 words, no explanations, no quotes, no extra text."
        else:
            system_prompt = """You are a helpful AI assistant named HenAi created by NexusCraft. 
When asked about your name, identity, or creator, respond with: 
'My name is HenAi, I'm an AI assistant created by NexusCraft, and I'm glad to be helping you! 😊 
Is there anything else you'd like to know, or anything else I can assist with today?'

Otherwise, provide helpful, contextually relevant responses using the full conversation history. 
Maintain context from the entire conversation, not just recent messages."""

        messages.append({"role": "system", "content": system_prompt})

        if context:
            # Use full context
            for ctx_msg in context:
                messages.append(ctx_msg)

        messages.append({"role": "user", "content": prompt})

        models = get_available_models()
        print(f"  Available free models: {models}")

        # Determine max_tokens based on request type
        if is_code_generation:
            max_tokens = 8000
        elif is_title_gen:
            max_tokens = 50
        else:
            max_tokens = 4000

        for model in models:
            try:
                print(f"  Trying model: {model}")
                temperature = 0.3 if is_title_gen else (0.5 if is_code_generation else 0.7)
                
                data = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }

                response = requests.post(url, json=data, headers=headers, timeout=60)

                if response.status_code == 200:
                    result = response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        message_content = result['choices'][0]['message']['content']
                        print(f"✓ OpenRouter success with {model}")
                        return message_content
                elif response.status_code == 429:
                    print(f"  Rate limited for {model}, trying next...")
                    continue
                else:
                    print(f"  Error {response.status_code}")
                    continue

            except Exception as e:
                print(f"  Exception with {model}: {e}")
                continue

        return None

    except Exception as e:
        print(f"OpenRouter error: {e}")
        return None


def query_ai_with_fallback(prompt, context=None, is_code_generation=False):
    """
    Query AI with appropriate service:
    - Code generation: ONLY OpenRouter (Pollinations is NOT used)
    - Non-code requests: Pollinations.ai first, then OpenRouter fallback
    """
    print(f"🤖 AI Request - Code Generation: {is_code_generation}")
    
    # For code generation requests - ONLY use OpenRouter
    if is_code_generation:
        print("🔄 Using OpenRouter for code generation...")
        response = query_openrouter(prompt, context, is_code_generation)
        if response:
            print("✅ OpenRouter code generation successful")
            return response
        else:
            print("❌ OpenRouter code generation failed")
            return f"I'm having trouble generating the code right now. Please try again or provide more details about what you need."
    
    # For NON-CODE requests (general chat, explanations, etc.) - use Pollinations.ai first
    else:
        # First try Pollinations.ai (faster for conversations)
        print("🔄 Trying Pollinations.ai for conversation...")
        messages = []
        if context:
            messages = context
        messages.append({"role": "user", "content": prompt})
        response = call_pollinations_ai(messages)
        if response:
            print("✅ Pollinations.ai conversation successful")
            return response
        
        # If Pollinations fails, fallback to OpenRouter
        print("⚠️ Pollinations.ai failed, falling back to OpenRouter...")
        response = query_openrouter(prompt, context, is_code_generation)
        if response:
            print("✅ OpenRouter conversation successful")
            return response
    
    # Ultimate fallback
    print("❌ Both AI services failed")
    return f"I'll help you with: {prompt}\n\nPlease provide more details so I can assist you better."


def generate_chat_title(messages):
    """Generate an intelligent title based on conversation context (max 5 words)"""
    try:
        # Extract the conversation context for title generation
        context_text = ""
        for msg in messages[-6:]:  # Look at last 6 messages for context
            if msg['role'] == 'user':
                context_text += msg['content'] + " "
        
        if not context_text.strip():
            # Fallback to first message if no context
            for msg in messages:
                if msg['role'] == 'user':
                    context_text = msg['content']
                    break
        
        # Create a prompt for title generation
        title_prompt = f"""Based on this conversation, generate a very short title (maximum 5 words). 
        The title should capture the main topic or purpose of the conversation. 
        Return ONLY the title, nothing else.
        
        Conversation context: {context_text[:500]}"""
        
        # Query AI for title generation (NOT code generation)
        title_response = query_ai_with_fallback(title_prompt, context=None, is_code_generation=False)
        
        if title_response:
            # Clean up the title - ensure max 5 words
            words = title_response.strip().split()
            if len(words) > 5:
                title = ' '.join(words[:5])
            else:
                title = title_response.strip()
            
            # Remove any quotes or extra punctuation
            title = title.strip('"\'').strip()
            
            # Ensure title is not empty
            if title and len(title) > 0:
                return title[:50]  # Cap at 50 chars for safety
        
        # Fallback to first user message if AI title generation fails
        for msg in messages:
            if msg['role'] == 'user':
                title = msg['content'][:40]
                if len(msg['content']) > 40:
                    title += "..."
                return title
        
        return "New Chat"
        
    except Exception as e:
        print(f"Error generating AI title: {e}")
        # Fallback to first user message
        for msg in messages:
            if msg['role'] == 'user':
                title = msg['content'][:40]
                if len(msg['content']) > 40:
                    title += "..."
                return title
        return "New Chat"


def is_code_generation_request(message):
    """
    Detect if the message is asking for code generation.
    Returns True only for explicit code generation requests.
    """
    message_lower = message.lower()
    
    # First, check for file analysis/summary requests - these are NOT code generation
    file_analysis_phrases = [
        'summarize', 'explain', 'what is', 'tell me about', 'describe',
        'extract', 'read', 'analyze', 'look at', 'examine', 'review',
        'content of', 'contains', 'in this file', 'from the file',
        'document says', 'file says'
    ]
    
    if any(phrase in message_lower for phrase in file_analysis_phrases):
        return False
    
    # Check if message is just asking about the file without code generation intent
    if len(message.split()) < 10:
        # Short messages about files are usually not code generation
        if 'file' in message_lower or 'document' in message_lower or 'content' in message_lower:
            return False
    
    # Code generation keywords - must be explicit about creating code
    code_keywords = [
        'create code', 'generate code', 'write code', 'build code', 'develop code',
        'write a program', 'create a program', 'generate a program',
        'write a script', 'create a script', 'generate a script',
        'write a function', 'create a function', 'generate a function',
        'write a class', 'create a class', 'generate a class',
        'implement', 'code for', 'program that', 'script that',
        'function that', 'class that', 'method that'
    ]
    
    # Also check for requests to create specific types of files
    if any(keyword in message_lower for keyword in code_keywords):
        return True
    
    # Check if message contains both a verb and a technology mention
    verbs = ['create', 'generate', 'write', 'build', 'develop', 'make', 'code']
    technologies = ['html', 'css', 'javascript', 'python', 'react', 'vue', 
                    'angular', 'node', 'express', 'django', 'flask']
    
    has_verb = any(verb in message_lower for verb in verbs)
    has_tech = any(tech in message_lower for tech in technologies)
    
    # Only consider it code generation if it's explicitly about creating something
    if has_verb and has_tech:
        return True
    
    return False


# ============= CODE EXECUTION =============

def execute_python_code(code):
    """Execute Python code safely and return output"""
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_file = f.name

        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            timeout=10
        )

        try:
            os.unlink(temp_file)
        except:
            pass

        if result.returncode == 0:
            return {
                'success': True,
                'output': result.stdout if result.stdout else "✓ Code executed successfully",
                'error': None
            }
        else:
            return {
                'success': False,
                'output': result.stdout,
                'error': result.stderr if result.stderr else "Execution failed"
            }
    except subprocess.TimeoutExpired:
        return {'success': False, 'output': '', 'error': '⏱️ Code execution timed out (10 seconds)'}
    except Exception as e:
        return {'success': False, 'output': '', 'error': str(e)}


# ============= WEB SEARCH AND EXTRACTION =============

def search_web(query):
    """Generate web search response"""
    return f"""🔍 **Web Search: "{query}"**

Use Google, DuckDuckGo, or Bing to find information.
You can also use `/extract [url]` to analyze specific websites.

Search links:
• Google: https://www.google.com/search?q={query.replace(' ', '+')}
• Wikipedia: https://en.wikipedia.org/wiki/{query.replace(' ', '_')}"""


def extract_web_content(url):
    """Extract content from a URL"""
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()

        text = re.sub(r'<[^>]+>', ' ', response.text)
        text = re.sub(r'\s+', ' ', text)
        content = text[:2000] + "..." if len(text) > 2000 else text

        return f"""📄 **Content from {url}**:

{content}"""

    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============= IMAGE ANALYSIS =============

def analyze_image_with_ai(image_content, image_name, photographer="Unknown", ocr_text=""):
    """Analyze an image using AI with OCR text - returns clean analysis without metadata"""
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "HenAi"
        }
        
        # Create clean prompt without asking for numbered sections
        if ocr_text and ocr_text.strip() and not ocr_text.startswith("[OCR extraction failed"):
            analysis_prompt = f"""Analyze the content of this image based on the text extracted from it.

Extracted text from the image:
{ocr_text[:2000]}

Please provide a natural, readable analysis of what this image contains. Focus on:
- What the image shows or represents based on the extracted text
- Any key information visible in the image
- The context or purpose of the image

Write in clear, well-formatted paragraphs. Do not use numbered lists, headers, or any markdown formatting. Just provide a natural analysis as if you're describing what you see."""
        else:
            # Extract meaningful description from filename
            import re
            name_without_ext = re.sub(r'\.[^.]+$', '', image_name)
            clean_name = re.sub(r'[_\-\.]', ' ', name_without_ext)
            clean_name = re.sub(r'\d+', '', clean_name).strip()
            
            analysis_prompt = f"""Analyze this image. The filename suggests it may be related to "{clean_name}".

Please provide a natural, readable analysis of:
- What this image likely shows or represents
- The subject matter or content
- Any notable characteristics

Write in clear, well-formatted paragraphs. Do not use numbered lists, headers, or any markdown formatting. Just provide a natural analysis as if you're describing what you see."""
        
        messages = [
            {"role": "system", "content": "You are an expert image analyst. Provide clean, natural analysis without any markdown formatting, headers, or numbered lists. Just write in plain paragraphs."},
            {"role": "user", "content": analysis_prompt}
        ]
        
        models_to_try = [
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.2-90b-vision-instruct:free",
            "microsoft/phi-3.5-mini-128k-instruct:free",
            "openrouter/free"
        ]
        
        for model in models_to_try:
            try:
                data = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
                
                response = requests.post(url, json=data, headers=headers, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        print(f"✓ Image analysis successful with {model}")
                        analysis = result['choices'][0]['message']['content']
                        
                        # Clean up any remaining markdown or numbered lists
                        import re
                        # Remove markdown headers
                        analysis = re.sub(r'^#{1,6}\s+.*?\n', '', analysis, flags=re.MULTILINE)
                        # Remove numbered list patterns like "1. " at start of lines
                        analysis = re.sub(r'^\d+\.\s+', '', analysis, flags=re.MULTILINE)
                        # Remove bullet points like "- " or "* " at start of lines
                        analysis = re.sub(r'^[\*\-]\s+', '', analysis, flags=re.MULTILINE)
                        # Remove any "**" bold markers
                        analysis = re.sub(r'\*\*([^*]+)\*\*', r'\1', analysis)
                        # Remove any remaining markdown artifacts
                        analysis = re.sub(r'`([^`]+)`', r'\1', analysis)
                        # Clean up multiple newlines
                        analysis = re.sub(r'\n{3,}', '\n\n', analysis)
                        # Trim whitespace
                        analysis = analysis.strip()
                        
                        return analysis
                elif response.status_code == 429:
                    print(f"Rate limited on {model}, trying next...")
                    continue
                else:
                    print(f"Model {model} failed with status {response.status_code}")
                    continue
                    
            except Exception as e:
                print(f"Error with {model}: {e}")
                continue
        
        # Fallback analysis
        if ocr_text and ocr_text.strip():
            # Clean OCR text for fallback
            import re
            clean_ocr = re.sub(r'\s+', ' ', ocr_text[:500]).strip()
            return f"The image contains readable text: {clean_ocr}"
        else:
            import re
            name_without_ext = re.sub(r'\.[^.]+$', '', image_name)
            clean_name = re.sub(r'[_\-\.]', ' ', name_without_ext)
            clean_name = re.sub(r'\d+', '', clean_name).strip()
            if clean_name:
                return f"This image appears to be related to {clean_name}."
            else:
                return "The image has been processed, but no readable text was detected."
        
    except Exception as e:
        print(f"Error analyzing image: {e}")
        return None
