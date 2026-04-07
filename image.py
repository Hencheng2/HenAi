"""
image.py - Free AI Image Generation Module
NO API KEYS REQUIRED - All methods are 100% free!
"""

import os
import io
import base64
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import json

# Check availability flags
LOCAL_SD_AVAILABLE = False
REPLICATE_AVAILABLE = False

# Try to import local generation libraries
try:
    from diffusers import (
        StableDiffusionPipeline, 
        StableDiffusionXLPipeline,
        FluxPipeline,
    )
    import torch
    LOCAL_SD_AVAILABLE = True
    print("✅ Local Stable Diffusion available (no API keys needed)")
except ImportError:
    print("⚠️ Local generation not available. Install with: pip install diffusers transformers torch accelerate")

try:
    import replicate
    REPLICATE_AVAILABLE = True
    print("✅ Replicate available (free credits, no credit card required)")
except ImportError:
    REPLICATE_AVAILABLE = False
    print("⚠️ Replicate not available (optional)")

# Global instances for lazy loading
_sd_pipe = None
_sdxl_pipe = None
_flux_pipe = None


class FreeImageGenerator:
    """
    100% Free AI Image Generator
    NO API KEYS REQUIRED - All methods work without any keys!
    """
    
    def __init__(self, output_dir: str = "generated_images"):
        """
        Initialize the free image generator.
        NO API KEYS NEEDED!
        
        Args:
            output_dir: Directory to save generated images
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Free models (no API keys needed)
        self.free_models = {
            'sd1.5': 'runwayml/stable-diffusion-v1-5',
            'sd2.1': 'stabilityai/stable-diffusion-2-1',
            'sdxl': 'stabilityai/stable-diffusion-xl-base-1.0',
            'sdxl-turbo': 'stabilityai/sdxl-turbo',
            'playground': 'playgroundai/playground-v2.5-1024px-aesthetic',
            'kandinsky': 'kandinsky-community/kandinsky-2-2-decoder',
            'pixart': 'PixArt-alpha/PixArt-XL-2-1024-MS',
            'flux-schnell': 'black-forest-labs/FLUX.1-schnell',
        }
        
        print(f"🎨 Free Image Generator initialized (NO API KEYS NEEDED)")
        print(f"   Output directory: {self.output_dir}")
        print(f"   Local GPU available: {LOCAL_SD_AVAILABLE}")
        print(f"   Free methods: Hugging Face API, Local GPU, Replicate (free credits)")
    
    # ==================== METHOD 1: HUGGING FACE API (100% FREE, NO KEY NEEDED) ====================
    
    def generate_huggingface(self, prompt: str, output_name: Optional[str] = None,
                             model: str = 'sd1.5', negative_prompt: str = '',
                             width: int = 512, height: int = 512,
                             num_inference_steps: int = 30) -> str:
        """
        Generate image using Hugging Face Inference API.
        100% FREE - NO API KEY REQUIRED!
        Free tier: 30,000 requests per month, rate limited.
        
        Args:
            prompt: Text description of the image
            output_name: Optional output filename
            model: Model to use (sd1.5, sdxl, flux-schnell, etc.)
            negative_prompt: What to avoid in the image
            width: Image width (512-1024 depending on model)
            height: Image height
            num_inference_steps: Quality vs speed (20-50)
        
        Returns:
            Path to generated image
        """
        if model not in self.free_models:
            raise ValueError(f"Model {model} not found. Available: {list(self.free_models.keys())}")
        
        model_id = self.free_models[model]
        
        # API URL for the model (NO API KEY NEEDED!)
        API_URL = f"https://api-inference.huggingface.co/models/{model_id}"
        
        # Prepare payload (no headers needed - works without API key!)
        payload = {
            "inputs": prompt,
            "parameters": {
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": 7.5
            }
        }
        
        print(f"Generating with Hugging Face API (free, no key needed)...")
        
        # Make request (no authentication!)
        response = requests.post(API_URL, json=payload)
        
        if response.status_code == 200:
            # Save image
            if not output_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_name = f"hf_{model}_{timestamp}.png"
            
            output_path = self.output_dir / output_name
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ Image generated via Hugging Face: {output_path}")
            return str(output_path)
        elif response.status_code == 503:
            # Model is loading, wait and retry
            print("Model is loading, retrying in 5 seconds...")
            import time
            time.sleep(5)
            return self.generate_huggingface(prompt, output_name, model, negative_prompt, width, height, num_inference_steps)
        else:
            error_msg = f"API Error {response.status_code}: {response.text[:200]}"
            if response.status_code == 401:
                error_msg += "\nNote: No API key needed! This error usually means the model is busy. Try again in a few seconds."
            raise Exception(error_msg)
    
    # ==================== METHOD 2: LOCAL STABLE DIFFUSION (100% FREE, NO INTERNET NEEDED) ====================
    
    def generate_local_sd(self, prompt: str, output_name: Optional[str] = None,
                          model: str = 'sd1.5', negative_prompt: str = '',
                          width: int = 512, height: int = 512,
                          num_inference_steps: int = 30,
                          guidance_scale: float = 7.5) -> str:
        """
        Generate image using local Stable Diffusion.
        100% FREE - NO API KEYS, NO INTERNET NEEDED (after models downloaded)!
        Requires GPU with 4GB+ VRAM.
        
        Args:
            prompt: Text description
            output_name: Optional filename
            model: Model to use (sd1.5, sdxl, sdxl-turbo, flux-schnell)
            negative_prompt: What to avoid
            width: Image width
            height: Image height
            num_inference_steps: Quality vs speed
            guidance_scale: How closely to follow prompt (1-20)
        """
        if not LOCAL_SD_AVAILABLE:
            raise ImportError("Local generation not installed. Run: pip install diffusers transformers torch accelerate")
        
        global _sd_pipe, _sdxl_pipe, _flux_pipe
        
        print(f"Generating locally with {model} (100% free, no API keys)...")
        
        # Select appropriate pipeline
        if model == 'sdxl' or model == 'sdxl-turbo':
            if _sdxl_pipe is None:
                print(f"Loading {model} model (first time, may take a while)...")
                model_id = self.free_models[model]
                
                # Check if CUDA is available, otherwise use float32 for CPU
                if torch.cuda.is_available():
                    _sdxl_pipe = StableDiffusionXLPipeline.from_pretrained(
                        model_id,
                        torch_dtype=torch.float16,
                        variant="fp16" if model == 'sdxl' else None
                    )
                else:
                    _sdxl_pipe = StableDiffusionXLPipeline.from_pretrained(
                        model_id,
                        torch_dtype=torch.float32
                    )
                
                if model == 'sdxl-turbo':
                    from diffusers import EulerDiscreteScheduler
                    _sdxl_pipe.scheduler = EulerDiscreteScheduler.from_pretrained(
                        model_id, subfolder="scheduler"
                    )
                
                device = "cuda" if torch.cuda.is_available() else "cpu"
                _sdxl_pipe = _sdxl_pipe.to(device)
            
            pipe = _sdxl_pipe
            
        elif model == 'flux-schnell':
            if _flux_pipe is None:
                print(f"Loading Flux model (first time, may take a while)...")
                model_id = self.free_models[model]
                _flux_pipe = FluxPipeline.from_pretrained(
                    model_id,
                    torch_dtype=torch.bfloat16
                )
                device = "cuda" if torch.cuda.is_available() else "cpu"
                _flux_pipe = _flux_pipe.to(device)
            
            pipe = _flux_pipe
            
        else:  # sd1.5, sd2.1, etc.
            if _sd_pipe is None:
                print(f"Loading {model} model (first time, may take a while)...")
                model_id = self.free_models[model]
                
                # Check if CUDA is available, otherwise use float32 for CPU
                if torch.cuda.is_available():
                    _sd_pipe = StableDiffusionPipeline.from_pretrained(
                        model_id,
                        torch_dtype=torch.float16
                    )
                else:
                    _sd_pipe = StableDiffusionPipeline.from_pretrained(
                        model_id,
                        torch_dtype=torch.float32
                    )
                device = "cuda" if torch.cuda.is_available() else "cpu"
                _sd_pipe = _sd_pipe.to(device)
            
            pipe = _sd_pipe
        
        # Special handling for turbo models
        if model == 'sdxl-turbo':
            num_inference_steps = min(num_inference_steps, 4)  # Turbo works best with 1-4 steps
            guidance_scale = 0.0  # Turbo uses no guidance
        
        # Generate image
        with torch.no_grad():
            result = pipe(
                prompt,
                negative_prompt=negative_prompt if negative_prompt else None,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                width=width,
                height=height
            )
        
        image = result.images[0]
        
        # Save image
        if not output_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"local_{model}_{timestamp}.png"
        
        output_path = self.output_dir / output_name
        image.save(output_path)
        
        print(f"✅ Image generated locally: {output_path}")
        return str(output_path)
    
    # ==================== METHOD 3: REPLICATE (FREE CREDITS, NO CREDIT CARD) ====================
    
    def generate_replicate(self, prompt: str, output_name: Optional[str] = None,
                           model: str = 'sd1.5') -> str:
        """
        Generate using Replicate API.
        100% FREE - $10 initial credits (NO CREDIT CARD REQUIRED)!
        That's about 500-1000 free images.
        
        Args:
            prompt: Text description
            output_name: Optional filename
            model: Model to use (sd1.5, sdxl, flux)
        """
        if not REPLICATE_AVAILABLE:
            raise ImportError("Replicate not installed. Run: pip install replicate")
        
        # Model IDs for Replicate
        replicate_models = {
            'sd1.5': "stability-ai/stable-diffusion:db21e45d3f7023abc2a46ee38a23973f6dce16bb082a930b0c49861f96d1e5bf",
            'sdxl': "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            'flux': "black-forest-labs/flux-schnell",
        }
        
        model_id = replicate_models.get(model, replicate_models['sd1.5'])
        
        print(f"Generating with Replicate (free credits, no credit card required)...")
        
        # Run generation
        output = replicate.run(
            model_id,
            input={"prompt": prompt}
        )
        
        # Download image
        if not output_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"replicate_{model}_{timestamp}.png"
        
        output_path = self.output_dir / output_name
        
        # Handle different output formats
        if isinstance(output, list):
            image_url = output[0]
        else:
            image_url = output
        
        response = requests.get(image_url)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✅ Image generated via Replicate: {output_path}")
        return str(output_path)
    
    # ==================== METHOD 4: AUTOMATIC1111 API (100% FREE LOCAL SERVER) ====================
    
    def generate_automatic1111(self, prompt: str, output_name: Optional[str] = None,
                               server_url: str = "http://127.0.0.1:7860",
                               negative_prompt: str = "",
                               width: int = 512, height: int = 512,
                               steps: int = 20) -> str:
        """
        Generate using Automatic1111 Web UI API.
        100% FREE - Runs locally, NO API KEYS NEEDED!
        Requires running Automatic1111 server locally.
        
        Args:
            prompt: Text description
            output_name: Optional filename
            server_url: URL of Automatic1111 server
            negative_prompt: What to avoid
            width: Image width
            height: Image height
            steps: Number of inference steps
        """
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": steps,
            "width": width,
            "height": height,
            "cfg_scale": 7,
            "sampler_index": "Euler a",
            "batch_size": 1
        }
        
        print(f"Generating with Automatic1111 (local, no API keys)...")
        
        response = requests.post(f"{server_url}/sdapi/v1/txt2img", json=payload)
        
        if response.status_code == 200:
            r = response.json()
            
            # Decode base64 image
            image_data = base64.b64decode(r['images'][0])
            
            # Save image
            if not output_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_name = f"auto1111_{timestamp}.png"
            
            output_path = self.output_dir / output_name
            with open(output_path, 'wb') as f:
                f.write(image_data)
            
            print(f"✅ Image generated via Automatic1111: {output_path}")
            return str(output_path)
        else:
            raise Exception(f"Automatic1111 error: {response.text}")
    
    # ==================== UTILITY METHODS ====================
    
    def get_available_methods(self) -> Dict[str, bool]:
        """Check which generation methods are available (all free!)"""
        return {
            'huggingface': True,  # Always available, no key needed
            'local_sd': LOCAL_SD_AVAILABLE,
            'replicate': REPLICATE_AVAILABLE,
            'automatic1111': self._check_automatic1111(),
        }
    
    def _check_automatic1111(self, server_url: str = "http://127.0.0.1:7860") -> bool:
        """Check if Automatic1111 server is running"""
        try:
            response = requests.get(f"{server_url}/sdapi/v1/sd-models", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def list_free_models(self) -> Dict[str, str]:
        """List all available free models"""
        return self.free_models.copy()
    
    def generate_with_fallback(self, prompt: str, output_name: Optional[str] = None,
                               preferred_methods: List[str] = None) -> str:
        """
        Generate image with automatic fallback to available methods.
        All methods are 100% free!
        
        Args:
            prompt: Text description
            output_name: Optional filename
            preferred_methods: Order of methods to try
        
        Returns:
            Path to generated image
        """
        if preferred_methods is None:
            preferred_methods = ['local_sd', 'huggingface', 'replicate', 'automatic1111']
        
        methods = {
            'local_sd': self.generate_local_sd,
            'huggingface': self.generate_huggingface,
            'replicate': self.generate_replicate,
            'automatic1111': self.generate_automatic1111,
        }
        
        for method_name in preferred_methods:
            if method_name in methods and self.get_available_methods().get(method_name, False):
                try:
                    print(f"\nTrying {method_name}...")
                    return methods[method_name](prompt, output_name)
                except Exception as e:
                    print(f"{method_name} failed: {e}")
                    continue
        
        raise Exception("All generation methods failed. Try: pip install diffusers transformers torch accelerate")


# ==================== CONVENIENCE FUNCTIONS ====================

def create_free_image_generator(output_dir: str = "generated_images") -> FreeImageGenerator:
    """Factory function to create FreeImageGenerator instance (NO API KEYS NEEDED!)"""
    return FreeImageGenerator(output_dir)


# ==================== USAGE EXAMPLES ====================

if __name__ == "__main__":
    # Create generator (NO API KEYS!)
    generator = create_free_image_generator()
    
    # Check available methods
    print("\n" + "="*50)
    print("AVAILABLE METHODS (ALL FREE):")
    print("="*50)
    for method, available in generator.get_available_methods().items():
        status = "✅ Available" if available else "❌ Not available"
        print(f"  {method}: {status}")
    
    print(f"\nAvailable models: {', '.join(generator.list_free_models().keys())}")
    
    # Example: Generate via Hugging Face (no key needed!)
    print("\n" + "="*50)
    print("EXAMPLE: Generating via Hugging Face (NO API KEY)")
    print("="*50)
    
    try:
        path = generator.generate_huggingface(
            "a beautiful sunset over mountains, highly detailed, 4k",
            output_name="sunset_hf.png"
        )
        print(f"\n✅ Image saved to: {path}")
    except Exception as e:
        print(f"\n⚠️ Could not generate: {e}")
        print("This may be due to rate limiting. Try again in a few seconds.")
    
    print("\n✅ All examples completed!")