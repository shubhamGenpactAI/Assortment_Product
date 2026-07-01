
#XAI_API_KEY = "gsk_ufsPm2gbsglUZMjG1psOWGdyb3FYiMvOJlau0TjpyPa4WKzzzgj"

import os
import sys
import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # loads .env from current directory

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    print("ERROR: OPENROUTER_API_KEY is not set.")
    print("Add it to .env or run:  $env:OPENROUTER_API_KEY='your_key_here'")
    sys.exit(1)

# Use corporate CA bundle to verify SSL (required on Genpact network).
# Set CORP_CERT_PATH in .env or as an environment variable pointing to your .pem/.crt file.
CORP_CERT_PATH = os.environ.get("CORP_CERT_PATH")
if not CORP_CERT_PATH:
    print("WARNING: CORP_CERT_PATH not set — falling back to verify=False (not recommended for production).")
    CORP_CERT_PATH = False

http_client = httpx.Client(verify=CORP_CERT_PATH)

client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1",
    http_client=http_client,
)

try:
    print("Sending request via OpenRouter...")

    response = client.chat.completions.create(
        model="google/gemma-4-31b-it:free",  # free model on OpenRouter
        messages=[
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": "Give me a quick 3-word greeting."}
        ],
        extra_headers={
            "HTTP-Referer": "https://your-app-url.com",
            "X-Title": "Your App Name",
        }
    )

    print("\nSuccess! Response from OpenRouter:")
    print(response.choices[0].message.content)

except Exception as e:
    print(f"\nError connecting to OpenRouter API: {e}")
