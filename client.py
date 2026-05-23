from groq import Groq
import pyttsx3
import os 
from dotenv import load_dotenv
load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

engine = pyttsx3.init()
voices = engine.getProperty('voices')       
engine.setProperty('voice', voices[1].id)

def speak(text):
    engine.say(text)
    engine.runAndWait()

response = client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[
        {"role": "user", "content": "Explain Python in simple words"}
    ]
)

print(response.choices[0].message.content)
speak(response.choices[0].message.content)