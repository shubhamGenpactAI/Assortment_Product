from openai import OpenAI
from dotenv import load_dotenv
import os

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