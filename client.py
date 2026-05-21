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