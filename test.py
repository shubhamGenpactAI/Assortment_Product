from openai import OpenAI
from dotenv import load_dotenv
import os

import certifi

cert_path = r"C:\Users\703442296\cert\corp-root.cer"
print("Path exists?", os.path.exists(cert_path))

os.environ["SSL_CERT_FILE"] = cert_path
os.environ["REQUESTS_CA_BUNDLE"] = cert_path

print("SSL_CERT_FILE is now:", os.environ.get("SSL_CERT_FILE"))

load_dotenv()  # loads variables from .env into environment

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"}
    ],
    temperature=0.7,
)

print(response.choices[0].message.content)