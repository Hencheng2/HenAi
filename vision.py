# vision.py - Multi-Model Vision Processor for HenAi
# Supports multiple vision models with automatic fallback
# No metadata analysis - pure image content understanding

import torch
from PIL import Image
import io
import base64
import requests
import re

# ============= TRY IMPORTS WITH FALLBACKS =============

# BLIP Model (Salesforce)
try:
    from transformers import BlipProcessor, BlipForConditionalGeneration
    BLIP_AVAILABLE = True
except ImportError:
    BLIP_AVAILABLE = False
    print("Warning: BLIP not available. Install with: pip install transformers")

# Florence-2 Model (Microsoft - more detailed)
try:
    from transformers import AutoProcessor, AutoModelForCausalLM
    FLORENCE_AVAILABLE = True
except ImportError:
    FLORENCE_AVAILABLE = False

# OFA Model (Microsoft - good all-rounder)
try:
    from transformers import OFATokenizer, OFAModel
    OFA_AVAILABLE = True
except ImportError:
    OFA_AVAILABLE = False

# Git (ViT + GPT2)
try:
    from transformers import GitProcessor, GitForCausalLM
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False


class VisionModel:
    """
    Multi-model vision processor with automatic fallback.
    Tries models in order: BLIP -> Florence-2 -> GIT -> Fallback text analysis
    """
    
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"🖼️ Initializing Vision Model on {self.device}...")
        
        self.models = {}
        self.current_model = None
        
        # Try to load BLIP (smallest, fastest)
        if BLIP_AVAILABLE:
            try:
                print("  Loading BLIP model...")
                self.models['blip'] = {
                    'processor': BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base"),
                    'model': BlipForConditionalGeneration.from_pretrained(
                        "Salesforce/blip-image-captioning-base",
                        torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                    ).to(self.device),
                    'name': 'BLIP'
                }
                self.models['blip']['model'].eval()
                print("  ✓ BLIP model loaded")
                self.current_model = 'blip'
            except Exception as e:
                print(f"  ✗ Failed to load BLIP: {e}")
        
        # Try to load Florence-2 (more detailed captions)
        if FLORENCE_AVAILABLE and not self.current_model:
            try:
                print("  Loading Florence-2 model...")
                self.models['florence'] = {
                    'processor': AutoProcessor.from_pretrained("microsoft/florence-2-base", trust_remote_code=True),
                    'model': AutoModelForCausalLM.from_pretrained(
                        "microsoft/florence-2-base",
                        trust_remote_code=True,
                        torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                    ).to(self.device),
                    'name': 'Florence-2'
                }
                self.models['florence']['model'].eval()
                print("  ✓ Florence-2 model loaded")
                self.current_model = 'florence'
            except Exception as e:
                print(f"  ✗ Failed to load Florence-2: {e}")
        
        # Try to load GIT (good for detailed descriptions)
        if GIT_AVAILABLE and not self.current_model:
            try:
                print("  Loading GIT model...")
                self.models['git'] = {
                    'processor': GitProcessor.from_pretrained("microsoft/git-base"),
                    'model': GitForCausalLM.from_pretrained(
                        "microsoft/git-base",
                        torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                    ).to(self.device),
                    'name': 'GIT'
                }
                self.models['git']['model'].eval()
                print("  ✓ GIT model loaded")
                self.current_model = 'git'
            except Exception as e:
                print(f"  ✗ Failed to load GIT: {e}")
        
        if not self.current_model:
            print("⚠️ No vision model loaded. Using fallback analysis.")
            self.current_model = None
    
    def get_vision_caption(self, image_bytes, max_length=100):
        """
        Generate a natural description of the image content.
        Returns a clean description without metadata.
        """
        if not self.current_model:
            return None
        
        try:
            # Load image
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            
            # Use the loaded model
            if self.current_model == 'blip':
                return self._caption_with_blip(image, max_length)
            elif self.current_model == 'florence':
                return self._caption_with_florence(image, max_length)
            elif self.current_model == 'git':
                return self._caption_with_git(image, max_length)
            else:
                return None
                
        except Exception as e:
            print(f"Error generating vision caption with {self.current_model}: {e}")
            # Try fallback to another model if available
            return self._try_fallback_model(image_bytes, max_length)
    
    def _caption_with_blip(self, image, max_length):
        """Generate caption using BLIP"""
        processor = self.models['blip']['processor']
        model = self.models['blip']['model']
        
        inputs = processor(images=image, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_length=max_length,
                num_beams=3,
                temperature=0.7,
                do_sample=True
            )
        
        caption = processor.decode(out[0], skip_special_tokens=True)
        return self._clean_caption(caption)
    
    def _caption_with_florence(self, image, max_length):
        """Generate detailed caption using Florence-2"""
        processor = self.models['florence']['processor']
        model = self.models['florence']['model']
        
        prompt = "<MORE_DETAILED_CAPTION>"
        inputs = processor(text=prompt, images=image, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=max_length,
                do_sample=False,
                num_beams=3
            )
        
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        # Remove the prompt from the output
        generated_text = generated_text.replace(prompt, "").strip()
        return self._clean_caption(generated_text)
    
    def _caption_with_git(self, image, max_length):
        """Generate caption using GIT"""
        processor = self.models['git']['processor']
        model = self.models['git']['model']
        
        inputs = processor(images=image, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            generated_ids = model.generate(
                pixel_values=inputs.pixel_values,
                max_length=max_length,
                num_beams=3,
                temperature=0.7
            )
        
        caption = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return self._clean_caption(caption)
    
    def _try_fallback_model(self, image_bytes, max_length):
        """Try to use a different model if the current one fails"""
        original_model = self.current_model
        available_models = list(self.models.keys())
        
        for model_name in available_models:
            if model_name != original_model:
                print(f"  Trying fallback model: {model_name}")
                self.current_model = model_name
                try:
                    result = self.get_vision_caption(image_bytes, max_length)
                    if result:
                        print(f"  ✓ Fallback to {model_name} successful")
                        return result
                except Exception as e:
                    print(f"  ✗ Fallback to {model_name} failed: {e}")
                    continue
        
        # Reset to original model
        self.current_model = original_model
        return None
    
    def _clean_caption(self, caption):
        """Clean the caption by removing metadata and markdown"""
        if not caption:
            return None
        
        # Remove common metadata patterns
        patterns_to_remove = [
            r'Photo by\s+\w+',  # Photo by [name]
            r'©\s+\d{4}\s+\w+',  # Copyright notices
            r'Image courtesy of\s+\w+',  # Courtesy notices
            r'Sourced from\s+\w+',  # Source notices
            r'Image from\s+\w+',  # Image from...
            r'Source:\s*\w+',  # Source:
            r'\(Photo credit:.*?\)',  # Photo credit
            r'\[.*?\]',  # Any bracketed text
            r'^\w+:\s*',  # "Label: " at start
            r'\*\*|\*|__|_',  # Markdown markers
        ]
        
        cleaned = caption
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Clean up multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Ensure first letter is capitalized
        if cleaned and len(cleaned) > 0:
            cleaned = cleaned[0].upper() + cleaned[1:] if cleaned[1:] else cleaned
        
        # Remove any trailing punctuation that looks like metadata
        cleaned = re.sub(r'\s*[|;:]\s*$', '', cleaned)
        
        return cleaned.strip()
    
    def analyze_image(self, image_bytes):
        """
        Generate a comprehensive, clean analysis of the image.
        Returns only the image content description, no metadata.
        """
        caption = self.get_vision_caption(image_bytes, max_length=120)
        
        if caption and len(caption) > 10:
            # Ensure the description is natural and doesn't mention metadata
            # Remove any remaining "a photo of", "an image of" patterns
            caption = re.sub(r'^(a|an)\s+(photo|picture|image)\s+of\s+', '', caption, flags=re.IGNORECASE)
            return caption
        
        return None


# Create global instance (lazy initialization)
_vision_model = None

def get_vision_model():
    """Get or create the global vision model instance"""
    global _vision_model
    if _vision_model is None:
        _vision_model = VisionModel()
    return _vision_model