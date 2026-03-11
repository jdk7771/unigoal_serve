
import os
import sys
from PIL import Image
import yaml

# Ensure project root is in path
sys.path.append(os.getcwd())

from src.utils.llm import LLM, VLM

def test_qwen_config():
    # Load config from file
    with open('configs/config_habitat.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    base_url = config['base_url']
    api_key = config['api_key']
    llm_model = config['llm_model']
    vlm_model = config['vlm_model']
    
    print(f"Testing LLM ({llm_model})...")
    llm = LLM(base_url, api_key, llm_model)
    try:
        response = llm("Hello, can you tell me what object a 'chair' is in one sentence?")
        print(f"LLM Response: {response}")
    except Exception as e:
        print(f"LLM Error: {e}")
        
    print("\nTesting VLM (" + vlm_model + ")...")
    vlm = VLM(base_url, api_key, vlm_model)
    try:
        # Load a test image from assets
        test_img = Image.open('assets/pipeline.png').convert('RGB')
        response = vlm("What is in this image?", test_img)
        print(f"VLM Response: {response}")
    except Exception as e:
        print(f"VLM Error: {e}")

if __name__ == "__main__":
    test_qwen_config()
