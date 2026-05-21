from groq import Groq
import pyttsx3

client = Groq(api_key="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")

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