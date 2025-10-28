#!/usr/bin/env python3
"""Debug Z.AI API response structure."""

import os
import json
import openai

# Set credentials
os.environ["ANTHROPIC_MODEL"] = "glm-4.6"
os.environ["ANTHROPIC_BASE_URL"] = "https://api.z.ai/api/anthropic"
os.environ["ANTHROPIC_AUTH_TOKEN"] = "665b963943b647dc9501dff942afb877.A47LrMc7sgGjyfBJ"

api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN")
base_url = os.environ.get("ANTHROPIC_BASE_URL")
model = os.environ.get("ANTHROPIC_MODEL")

print("Testing Z.AI API response structure...")
print(f"Base URL: {base_url}")
print(f"Model: {model}")

client = openai.OpenAI(api_key=api_key, base_url=base_url)

try:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": "Say hello"}
        ],
        max_tokens=50
    )
    
    print("\n✅ API Response received!")
    print(f"Response type: {type(response)}")
    print(f"Response dir: {[x for x in dir(response) if not x.startswith('_')]}")
    
    # Try to access response attributes
    print(f"\nResponse attributes:")
    try:
        print(f"  id: {response.id}")
    except: print("  id: N/A")
    
    try:
        print(f"  model: {response.model}")
    except: print("  model: N/A")
    
    try:
        print(f"  choices: {response.choices}")
    except: print("  choices: N/A")
    
    try:
        print(f"  usage: {response.usage}")
    except: print("  usage: N/A")
    
    # Try to convert to dict
    try:
        response_dict = response.model_dump() if hasattr(response, 'model_dump') else response.dict()
        print(f"\nResponse as dict:")
        print(json.dumps(response_dict, indent=2, default=str))
    except Exception as e:
        print(f"Could not convert to dict: {e}")
        
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

