import os

from dotenv import load_dotenv

load_dotenv()

if not os.getenv("GROQ_API_KEY"):
    raise SystemExit(
        "GROQ_API_KEY not found. Create a .env file (see .env.example) "
        "with your key from https://console.groq.com/keys"
    )

from langchain_groq import ChatGroq

MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
print(f"Testing model: {MODEL_NAME}")

llm = ChatGroq(
    model=MODEL_NAME,
    temperature=0,
)

response = llm.invoke("Reply with exactly the word: CONNECTED")
print("Raw response:", response.content)

if "CONNECTED" in response.content.upper():
    print("\n✅ Success -- your API key works and the model is reachable.")
else:
    print("\n⚠️ Got a response but not the expected content. Check output above.")
