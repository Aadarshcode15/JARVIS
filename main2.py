import speech_recognition as sr
import webbrowser
import requests
import datetime
import os
import time
import asyncio
import tempfile
import subprocess
import ctypes
import ctypes.wintypes
import threading
import pyperclip
import psutil
import base64
import screen_brightness_control as sbc
import pyautogui
import edge_tts
import pygame
import tkinter as tk
import tkinter.font as tkfont
import math
import random
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import pywhatkit
from ollama import Client as OllamaClient
from groq import Groq

# ──────────────────────────────────────────────
# CONFIG  — fill in your keys here
# ──────────────────────────────────────────────
GROQ_API_KEY        = os.getenv("GROQ_API_KEY",        "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")
NEWS_API_KEY        = os.getenv("NEWS_API_KEY",        "10178009bb78d9ba7e4b5c50e53db161")
WEATHER_API_KEY     = os.getenv("WEATHER_API_KEY",     "fbdd8dfa5799482ed1a2eeff7fc06f4f")
SPOTIFY_CLIENT_ID   = os.getenv("SPOTIFY_CLIENT_ID",   "a2dbe34e9bc04599bb24ee4e18df5472")  # Spotify developer dashboard
SPOTIFY_SECRET      = os.getenv("SPOTIFY_SECRET",      "7976fba120394511bfda909ca2863d6f")
SPOTIFY_REDIRECT    = "https://127.0.0.1:8888/callback"

OLLAMA_MODEL  = "gemma4:e4b"
OLLAMA_HOST   = "http://localhost:11434"
GROQ_MODEL    = "llama-3.1-8b-instant"
VISION_MODEL  = "meta-llama/llama-4-scout-17b-16e-instruct"   # Groq vision model for Friday

VOICE_JARVIS  = "en-GB-RyanNeural"
VOICE_FRIDAY  = "en-US-AriaNeural"

WAKE_JARVIS_KW = "jarvis"
WAKE_FRIDAY_KW = "friday"

MAX_NEWS = 5

MUSIC_LIBRARY = {
    "believer":     "https://www.youtube.com/watch?v=7wtfhZwyrcc",
    "shape of you": "https://www.youtube.com/watch?v=JGwWNGJdvx8",
}

APPS = {
    "notepad":            "notepad.exe",
    "calculator":         "calc.exe",
    "paint":              "mspaint.exe",
    "word":               "winword.exe",
    "excel":              "excel.exe",
    "powerpoint":         "powerpnt.exe",
    "file explorer":      "explorer.exe",
    "task manager":       "taskmgr.exe",
    "vs code":            "code",
    "visual studio code": "code",
    "camera":             "microsoft.windows.camera:",
    "settings":           "ms-settings:",
}

SITES = {
    "google":    "https://google.com",
    "facebook":  "https://facebook.com",
    "youtube":   "https://youtube.com",
    "linkedin":  "https://linkedin.com",
    "github":    "https://github.com",
    "twitter":   "https://twitter.com",
    "instagram": "https://instagram.com",
}

# WhatsApp contacts — add your contacts here
# Format: "name as you'll say it": "+countrycode number"
WHATSAPP_CONTACTS = {
    "AG":    "+917028612187",
    "M": "+918308818512",
    "dad":    "+91XXXXXXXXXX",
    "friend": "+91XXXXXXXXXX",
    # add more contacts here ...
}

# ──────────────────────────────────────────────
# ACTIVE ASSISTANT STATE
# ──────────────────────────────────────────────
active_assistant = "jarvis"

def set_active(name):
    global active_assistant
    active_assistant = name

def current_voice():
    return VOICE_FRIDAY if active_assistant == "friday" else VOICE_JARVIS

# ──────────────────────────────────────────────
# UI STATE
# ──────────────────────────────────────────────
class State:
    IDLE      = "idle"
    LISTENING = "listening"
    THINKING  = "thinking"
    SPEAKING  = "speaking"

ui_state   = State.IDLE
last_heard = ""
last_reply = ""
last_who   = ""
_ui_root   = None

def set_state(s):
    global ui_state
    ui_state = s

def set_last(heard="", reply="", who=""):
    global last_heard, last_reply, last_who
    if heard: last_heard = heard
    if reply: last_reply = reply
    if who:   last_who   = who

# ──────────────────────────────────────────────
# SPEECH ENGINE
# ──────────────────────────────────────────────
pygame.mixer.init()

async def _synthesise(text, filepath, voice):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filepath)

def speak(text: str, voice: str = None) -> None:
    if voice is None:
        voice = current_voice()
    who = "Friday" if voice == VOICE_FRIDAY else "Jarvis"
    print(f"[{who}] {text}")
    set_state(State.SPEAKING)
    set_last(reply=text, who=who.lower())
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp_path = f.name
        asyncio.run(_synthesise(text, tmp_path, voice))
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.music.unload()
        os.remove(tmp_path)
    except Exception as e:
        print(f"[TTS Error] {e}")
    set_state(State.IDLE)

def speak_jarvis(text): speak(text, VOICE_JARVIS)
def speak_friday(text): speak(text, VOICE_FRIDAY)

# ──────────────────────────────────────────────
# SPOTIFY
# ──────────────────────────────────────────────
_sp = None

def _get_spotify():
    global _sp
    if _sp is None:
        try:
            _sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_SECRET,
                redirect_uri=SPOTIFY_REDIRECT,
                scope="user-modify-playback-state user-read-playback-state user-read-currently-playing"
            ))
        except Exception as e:
            print(f"[Spotify Init Error] {e}")
    return _sp

def handle_spotify(command: str) -> bool:
    triggers = ("spotify", "song", "music", "play ", "pause music",
                "stop music", "next song", "skip song", "previous song",
                "resume music", "what song", "current song")
    if not any(t in command for t in triggers):
        return False

    sp = _get_spotify()
    if sp is None:
        speak("Spotify is not connected. Please set your Spotify API keys in config.")
        return True

    try:
        # ── what's playing ──
        if "what song" in command or "current song" in command or "what's playing" in command:
            current = sp.current_playback()
            if current and current.get("item"):
                track  = current["item"]["name"]
                artist = current["item"]["artists"][0]["name"]
                speak(f"Currently playing {track} by {artist}.")
            else:
                speak("Nothing is playing on Spotify right now.")
            return True

        # ── pause / stop ──
        if "pause" in command or ("stop" in command and "music" in command):
            sp.pause_playback()
            speak("Paused.")
            return True

        # ── resume ──
        if "resume" in command or "continue" in command:
            sp.start_playback()
            speak("Resuming.")
            return True

        # ── next ──
        if "next" in command or "skip" in command:
            sp.next_track()
            speak("Next track.")
            return True

        # ── previous ──
        if "previous" in command or "last song" in command or "go back" in command:
            sp.previous_track()
            speak("Previous track.")
            return True

        # ── volume ──
        if "spotify volume" in command:
            words = command.split()
            for w in words:
                if w.isdigit():
                    level = max(0, min(100, int(w)))
                    sp.volume(level)
                    speak(f"Spotify volume set to {level}.")
                    return True

        # ── play a song ──
        # "play Blinding Lights on Spotify" or "play Blinding Lights"
        query = command
        for filler in ("play", "on spotify", "spotify", "song", "music", "the song"):
            query = query.replace(filler, "")
        query = query.strip()

        if query:
            results = sp.search(q=query, limit=1, type="track")
            tracks  = results.get("tracks", {}).get("items", [])
            if tracks:
                track_uri = tracks[0]["uri"]
                track_name = tracks[0]["name"]
                artist_name = tracks[0]["artists"][0]["name"]
                sp.start_playback(uris=[track_uri])
                speak(f"Playing {track_name} by {artist_name} on Spotify.")
            else:
                speak(f"Couldn't find {query} on Spotify.")

    except spotipy.exceptions.SpotifyException as e:
        print(f"[Spotify Error] {e}")
        speak("Spotify error. Make sure Spotify is open and playing on a device.")
    except Exception as e:
        print(f"[Spotify Error] {e}")
        speak("Something went wrong with Spotify.")
    return True

# ──────────────────────────────────────────────
# WHATSAPP
# ──────────────────────────────────────────────
def handle_whatsapp(command: str) -> bool:
    if "whatsapp" not in command and "message" not in command and "send" not in command:
        return False

    try:
        # Parse: "send [contact] [message]" or "whatsapp [contact] [message]"
        contact_found = None
        phone_number  = None

        for name, number in WHATSAPP_CONTACTS.items():
            if name.lower() in command:
                contact_found = name
                phone_number  = number
                break

        if not phone_number:
            speak("I didn't recognise that contact. Please add them to WHATSAPP_CONTACTS in config.")
            return True

        # Extract message — everything after the contact name
        msg_start = command.lower().find(contact_found.lower()) + len(contact_found)
        message   = command[msg_start:].strip()

        # Strip common prefixes
        for prefix in ("saying", "that", "to say", "with", ":"):
            if message.startswith(prefix):
                message = message[len(prefix):].strip()

        if not message:
            speak(f"What would you like to say to {contact_found}?")
            return True

        speak(f"Sending WhatsApp message to {contact_found}.")
        pywhatkit.sendwhatmsg_instantly(
            phone_number, message,
            wait_time=12,
            tab_close=True,
            close_time=4
        )
        speak("Message sent.")

    except Exception as e:
        print(f"[WhatsApp Error] {e}")
        speak("Sorry, I couldn't send the WhatsApp message.")
    return True

# ──────────────────────────────────────────────
# VISION  — describe screen via Groq
# ──────────────────────────────────────────────
def handle_vision(command: str) -> bool:
    vision_triggers = (
        "what's on my screen", "describe my screen", "what do you see",
        "look at my screen", "read my screen", "analyse my screen",
        "what is on screen", "screen description"
    )
    if not any(t in command for t in vision_triggers):
        return False

    speak_friday("Let me take a look.")
    set_state(State.THINKING)

    try:
        # Take screenshot
        screenshot = pyautogui.screenshot()

        # Encode to base64
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
            tmp_path = f.name
        screenshot.save(tmp_path)

        with open(tmp_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        os.remove(tmp_path)

        # Send to Groq vision
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": (
                                "You are Friday, a voice assistant. "
                                "Describe what is on this screen in 2-3 short spoken sentences. "
                                "Be concise — this will be spoken aloud. "
                                "No markdown, no bullet points."
                            )
                        }
                    ]
                }
            ],
            max_tokens=200
        )
        description = response.choices[0].message.content
        speak_friday(description)

    except Exception as e:
        print(f"[Vision Error] {e}")
        speak_friday("Sorry, I couldn't analyse the screen right now.")
    return True

# ──────────────────────────────────────────────
# AI BACKENDS
# ──────────────────────────────────────────────
JARVIS_SYSTEM = (
    "You are Jarvis, a male voice assistant running locally on the user's laptop. "
    "You specialise in system tasks and technical questions. "
    "Keep answers short — 2-3 sentences max. No markdown or special characters."
)

FRIDAY_SYSTEM = (
    "You are Friday, a female voice assistant powered by cloud AI. "
    "You specialise in fast answers, web searches, and general knowledge. "
    "Keep answers short — 2-3 sentences max. No markdown or special characters."
)

def ai_jarvis(command: str) -> str:
    set_state(State.THINKING)
    try:
        client = OllamaClient(host=OLLAMA_HOST)
        resp = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": JARVIS_SYSTEM},
                {"role": "user",   "content": command},
            ],
        )
        return resp["message"]["content"]
    except Exception as e:
        print(f"[Jarvis AI Error] {e}")
        return "Sorry, my local model is not responding. Make sure Ollama is running."

def ai_friday(command: str) -> str:
    set_state(State.THINKING)
    try:
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": FRIDAY_SYSTEM},
                {"role": "user",   "content": command},
            ],
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[Friday AI Error] {e}")
        return "Sorry, I couldn't reach the cloud. Check your Groq API key."

# ──────────────────────────────────────────────
# VOLUME HELPER
# ──────────────────────────────────────────────
def _set_volume_exact(level: int) -> None:
    try:
        subprocess.run(
            ["nircmd.exe", "setsysvolume", str(int(level / 100 * 65535))],
            check=True, capture_output=True
        )
    except Exception:
        pyautogui.press("volumedown", presses=50)
        if int(level / 2) > 0:
            pyautogui.press("volumeup", presses=int(level / 2))

# ──────────────────────────────────────────────
# COMMAND HANDLERS
# ──────────────────────────────────────────────
def handle_weather(command: str) -> bool:
    if "weather" not in command:
        return False
    try:
        loc  = requests.get("http://ip-api.com/json/", timeout=5).json()
        city = loc.get("city", "your location")
        if WEATHER_API_KEY == "YOUR_OPENWEATHERMAP_KEY":
            speak("Weather API key not set. Add your free OpenWeatherMap key in config.")
            return True
        url  = (f"https://api.openweathermap.org/data/2.5/weather"
                f"?q={city}&appid={WEATHER_API_KEY}&units=metric")
        data = requests.get(url, timeout=5).json()
        temp, feels = round(data["main"]["temp"]), round(data["main"]["feels_like"])
        desc, hum   = data["weather"][0]["description"], data["main"]["humidity"]
        speak(f"In {city}, it's {temp}°C with {desc}. Feels like {feels}°, humidity {hum}%.")
    except Exception as e:
        print(f"[Weather Error] {e}")
        speak("Sorry, couldn't fetch the weather.")
    return True

def handle_battery(command: str) -> bool:
    if "battery" not in command:
        return False
    try:
        bat = psutil.sensors_battery()
        if bat is None:
            speak("No battery detected."); return True
        pct = int(bat.percent)
        if bat.power_plugged:
            time_msg = "and charging" if pct < 100 else "and fully charged"
        elif bat.secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
            time_msg = ""
        else:
            h, m = bat.secsleft // 3600, (bat.secsleft % 3600) // 60
            time_msg = f"with about {h}h {m}m remaining"
        speak(f"Battery at {pct}%, {'plugged in' if bat.power_plugged else 'on battery'} {time_msg}.".strip())
    except Exception as e:
        print(f"[Battery Error] {e}")
        speak("Couldn't read battery.")
    return True

def handle_clipboard(command: str) -> bool:
    if "clipboard" not in command:
        return False
    try:
        if any(k in command for k in ("read", "what", "paste")):
            content = pyperclip.paste()
            if not content.strip():
                speak("Clipboard is empty."); return True
            snippet = content[:200] + ("..." if len(content) > 200 else "")
            speak(f"Clipboard says: {snippet}")
        elif "clear" in command:
            pyperclip.copy(""); speak("Clipboard cleared.")
    except Exception as e:
        print(f"[Clipboard Error] {e}")
        speak("Couldn't access clipboard.")
    return True

def handle_open_site(command: str) -> bool:
    for site, url in SITES.items():
        if f"open {site}" in command:
            speak(f"Opening {site}"); webbrowser.open(url); return True
    return False

def handle_open_app(command: str) -> bool:
    for app_name, exe in APPS.items():
        if app_name in command:
            speak(f"Opening {app_name}")
            try:
                os.startfile(exe) if exe.endswith(":") else subprocess.Popen(exe, shell=True)
            except Exception as e:
                speak(f"Couldn't open {app_name}"); print(f"[App Error] {e}")
            return True
    return False

def handle_volume(command: str) -> bool:
    if "volume" not in command and "mute" not in command:
        return False
    if "spotify" in command:   # handled by Spotify handler
        return False
    try:
        if "unmute" in command:
            pyautogui.press("volumemute"); speak("Unmuted."); return True
        if "mute" in command:
            pyautogui.press("volumemute"); speak("Muted."); return True
        for w in command.split():
            if w.isdigit():
                level = max(0, min(100, int(w)))
                _set_volume_exact(level); speak(f"Volume set to {level}."); return True
        if any(k in command for k in ("up", "increase", "raise")):
            pyautogui.press("volumeup", presses=5); speak("Volume up."); return True
        if any(k in command for k in ("down", "decrease", "lower")):
            pyautogui.press("volumedown", presses=5); speak("Volume down."); return True
    except Exception as e:
        print(f"[Volume Error] {e}"); speak("Couldn't control volume.")
    return True

def handle_brightness(command: str) -> bool:
    if "brightness" not in command:
        return False
    try:
        cur = sbc.get_brightness(display=0)[0]
        for w in command.split():
            if w.isdigit():
                lvl = max(0, min(100, int(w)))
                sbc.set_brightness(lvl, display=0); speak(f"Brightness set to {lvl}."); return True
        if any(k in command for k in ("up", "increase", "raise")):
            sbc.set_brightness(min(100, cur+10), display=0); speak("Brightness increased."); return True
        if any(k in command for k in ("down", "decrease", "lower")):
            sbc.set_brightness(max(0, cur-10), display=0); speak("Brightness decreased."); return True
    except Exception as e:
        print(f"[Brightness Error] {e}"); speak("Couldn't control brightness.")
    return True

def handle_screenshot(command: str) -> bool:
    if "screenshot" not in command and "capture screen" not in command:
        return False
    try:
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)
        desktop = buf.value if os.path.exists(buf.value) else os.path.dirname(os.path.abspath(__file__))
        fname = f"Screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        fpath = os.path.join(desktop, fname)
        pyautogui.screenshot(fpath)
        speak(f"Screenshot saved as {fname}")
        print(f"[Screenshot] {fpath}")
    except Exception as e:
        print(f"[Screenshot Error] {e}"); speak("Couldn't take screenshot.")
    return True

def handle_play_music(command: str) -> bool:
    if not command.startswith("play"):
        return False
    if any(k in command for k in ("spotify", "song", "music")):
        return False   # let Spotify handler deal with it
    query = command.replace("play", "").strip().lower()
    for song, url in MUSIC_LIBRARY.items():
        if query == song or query in song:
            speak(f"Playing {song}"); webbrowser.open(url); return True
    return False   # fall through to Spotify handler

def handle_news() -> None:
    try:
        url = (f"https://gnews.io/api/v4/top-headlines"
               f"?category=general&lang=en&country=in&max={MAX_NEWS}&apikey={NEWS_API_KEY}")
        articles = requests.get(url, timeout=5).json().get("articles", [])
        if not articles:
            speak("No news found."); return
        speak(f"Here are {len(articles)} headlines.")
        for i, a in enumerate(articles, 1):
            speak(f"Headline {i}: {a['title']}")
    except Exception as e:
        print(f"[News Error] {e}"); speak("Couldn't fetch news.")

def handle_time_date(command: str) -> bool:
    now = datetime.datetime.now()
    if "time" in command:
        speak(f"It's {now.strftime('%I:%M %p')}."); return True
    if "date" in command:
        speak(f"Today is {now.strftime('%A, %B %d, %Y')}."); return True
    return False

def handle_search(command: str) -> bool:
    if "youtube search" in command:
        q = command.replace("youtube search", "").strip()
        speak(f"Searching YouTube for {q}")
        webbrowser.open(f"https://www.youtube.com/results?search_query={q.replace(' ','+')}"); return True
    if "search" in command:
        q = command.replace("search", "").strip()
        speak(f"Searching for {q}")
        webbrowser.open(f"https://www.google.com/search?q={q.replace(' ','+')}"); return True
    return False

def handle_exit(command: str) -> bool:
    if any(k in command for k in ("stop", "exit", "goodbye", "shut down")):
        speak("Signing off. Have a great day!"); raise SystemExit
    if any(k in command for k in ("sleep", "pause")):
        speak("Going to sleep."); return True
    return False

# ──────────────────────────────────────────────
# COMMAND ROUTERS
# ──────────────────────────────────────────────
def process_jarvis(command: str) -> None:
    c = command.lower().strip()
    print(f"[Jarvis Command] {c}")
    set_last(heard=command, who="jarvis")

    if handle_exit(c):        return
    if handle_time_date(c):   return
    if handle_weather(c):     return
    if handle_battery(c):     return
    if handle_clipboard(c):   return
    if handle_volume(c):      return
    if handle_brightness(c):  return
    if handle_screenshot(c):  return
    if handle_open_app(c):    return
    if handle_open_site(c):   return
    if handle_spotify(c):     return
    if handle_whatsapp(c):    return
    if handle_play_music(c):  return
    if handle_search(c):      return
    if "news" in c:
        handle_news(); return

    speak_jarvis(ai_jarvis(command))

def process_friday(command: str) -> None:
    c = command.lower().strip()
    print(f"[Friday Command] {c}")
    set_last(heard=command, who="friday")

    if handle_exit(c):       return
    if handle_time_date(c):  return
    if handle_weather(c):    return
    if handle_vision(c):     return
    if handle_spotify(c):    return
    if handle_whatsapp(c):   return
    if handle_search(c):     return
    if handle_open_site(c):  return
    if "news" in c:
        handle_news(); return

    speak_friday(ai_friday(command))

# ──────────────────────────────────────────────
# LISTEN HELPER  (for commands after wake word)
# ──────────────────────────────────────────────
_recognizer    = sr.Recognizer()
_noise_done    = False

def _calibrate_once():
    global _noise_done
    if not _noise_done:
        with sr.Microphone() as source:
            _recognizer.adjust_for_ambient_noise(source, duration=0.5)
        _noise_done = True

def listen_for_command(timeout=6, phrase_limit=10):
    with sr.Microphone() as source:
        try:
            audio = _recognizer.listen(source, timeout=timeout,
                                       phrase_time_limit=phrase_limit)
            return _recognizer.recognize_google(audio)
        except sr.WaitTimeoutError:  return None
        except sr.UnknownValueError: return None
        except sr.RequestError as e:
            print(f"[STT Error] {e}"); return None

def flush_mic(duration=0.2):
    try:
        with sr.Microphone() as source:
            _recognizer.listen(source, timeout=duration, phrase_time_limit=duration)
    except Exception:
        pass

# ──────────────────────────────────────────────
# AUDIO LOOP  — Google STT wake word detection
# ──────────────────────────────────────────────
def audio_loop():
    recognizer = sr.Recognizer()
    print("[Calibrating microphone...]")
    _calibrate_once()
    speak_jarvis(f"Dual assistant online. Say {WAKE_JARVIS_KW} for Jarvis, or {WAKE_FRIDAY_KW} for Friday.")

    while True:
        try:
            set_state(State.IDLE)
            with sr.Microphone() as source:
                try:
                    audio = recognizer.listen(source, timeout=3, phrase_time_limit=3)
                    word  = recognizer.recognize_google(audio)
                except Exception:
                    continue

            print(f"[Heard] {word}")
            wl = word.lower()

            if WAKE_JARVIS_KW in wl:
                set_active("jarvis")
                speak_jarvis("Yes?")
            elif WAKE_FRIDAY_KW in wl:
                set_active("friday")
                speak_friday("Yes?")
            else:
                continue

            time.sleep(0.5)
            flush_mic(0.2)

            set_state(State.LISTENING)
            print("[Listening for command...]")
            command = listen_for_command()

            if not command:
                speak("I didn't catch that.")
                continue

            print(f"[You said] {command}")
            if active_assistant == "friday":
                process_friday(command)
            else:
                process_jarvis(command)

            time.sleep(0.8)

        except SystemExit:
            if _ui_root: _ui_root.after(0, _ui_root.destroy)
            break
        except KeyboardInterrupt:
            speak("Shutting down.")
            break
        except Exception as e:
            print(f"[Unexpected Error] {e}")

# ──────────────────────────────────────────────
# UI  — Sci-Fi Dual-Assistant Dashboard
# ──────────────────────────────────────────────
def run_ui():
    global _ui_root
    root = tk.Tk()
    _ui_root = root
    root.title("J.A.R.V.I.S  +  F.R.I.D.A.Y")
    root.configure(bg="#020b14")
    root.geometry("920x620")
    root.resizable(False, False)

    C_BG      = "#020b14"
    C_PANEL   = "#040f1c"
    C_JARVIS  = "#00d4ff"
    C_FRIDAY  = "#ff69b4"
    C_DIM     = "#0d2535"
    C_DIM_TXT = "#2a4a5e"
    C_GOLD    = "#f0a500"
    C_GREEN   = "#00ff88"
    C_TEXT    = "#a0cfe0"

    try:
        FNT_TITLE  = tkfont.Font(family="Courier New", size=17, weight="bold")
        FNT_SUB    = tkfont.Font(family="Courier New", size=8)
        FNT_STATUS = tkfont.Font(family="Courier New", size=10, weight="bold")
        FNT_LOG    = tkfont.Font(family="Courier New", size=9)
        FNT_BADGE  = tkfont.Font(family="Courier New", size=8, weight="bold")
    except:
        FNT_TITLE  = tkfont.Font(size=17, weight="bold")
        FNT_SUB    = tkfont.Font(size=8)
        FNT_STATUS = tkfont.Font(size=10, weight="bold")
        FNT_LOG    = tkfont.Font(size=9)
        FNT_BADGE  = tkfont.Font(size=8, weight="bold")

    # Title bar
    top = tk.Frame(root, bg=C_BG)
    top.pack(fill=tk.X, padx=20, pady=(14,0))
    tk.Label(top, text="J.A.R.V.I.S", font=FNT_TITLE, bg=C_BG, fg=C_JARVIS).pack(side=tk.LEFT)
    tk.Label(top, text=" + ",          font=FNT_TITLE, bg=C_BG, fg=C_DIM_TXT).pack(side=tk.LEFT)
    tk.Label(top, text="F.R.I.D.A.Y", font=FNT_TITLE, bg=C_BG, fg=C_FRIDAY).pack(side=tk.LEFT)
    clock_var = tk.StringVar()
    tk.Label(top, textvariable=clock_var, font=FNT_SUB, bg=C_BG, fg=C_TEXT).pack(side=tk.RIGHT, pady=(8,0))

    d = tk.Canvas(root, height=1, bg=C_BG, highlightthickness=0)
    d.pack(fill=tk.X, padx=20)
    d.create_line(0, 0, 920, 0, fill=C_DIM_TXT)

    body = tk.Frame(root, bg=C_BG)
    body.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    # Left panel
    left = tk.Frame(body, bg=C_BG, width=230)
    left.pack(side=tk.LEFT, fill=tk.Y)
    left.pack_propagate(False)

    tk.Label(left, text="ACTIVE", font=FNT_SUB, bg=C_BG, fg=C_DIM_TXT).pack(anchor=tk.W)
    active_var = tk.StringVar(value="● JARVIS")
    active_lbl = tk.Label(left, textvariable=active_var, font=FNT_STATUS, bg=C_BG, fg=C_JARVIS)
    active_lbl.pack(anchor=tk.W, pady=(2,10))

    tk.Label(left, text="AUDIO INPUT", font=FNT_SUB, bg=C_BG, fg=C_DIM_TXT).pack(anchor=tk.W)
    vis = tk.Canvas(left, width=210, height=120, bg=C_PANEL,
                    highlightthickness=1, highlightbackground=C_DIM_TXT)
    vis.pack(pady=(4,10))

    tk.Label(left, text="STATE", font=FNT_SUB, bg=C_BG, fg=C_DIM_TXT).pack(anchor=tk.W)
    state_var = tk.StringVar(value="● STANDBY")
    state_lbl = tk.Label(left, textvariable=state_var, font=FNT_STATUS, bg=C_BG, fg=C_DIM_TXT)
    state_lbl.pack(anchor=tk.W, pady=(2,10))

    tk.Label(left, text="WAKE WORDS", font=FNT_SUB, bg=C_BG, fg=C_DIM_TXT).pack(anchor=tk.W)
    tk.Label(left, text=f'"{WAKE_JARVIS_KW.upper()}"  →  Jarvis',
             font=FNT_BADGE, bg=C_BG, fg=C_JARVIS).pack(anchor=tk.W, pady=(2,0))
    tk.Label(left, text=f'"{WAKE_FRIDAY_KW.upper()}"  →  Friday',
             font=FNT_BADGE, bg=C_BG, fg=C_FRIDAY).pack(anchor=tk.W, pady=(0,10))

    tk.Label(left, text="MODELS", font=FNT_SUB, bg=C_BG, fg=C_DIM_TXT).pack(anchor=tk.W)
    tk.Label(left, text=f"⚙  {OLLAMA_MODEL}",  font=FNT_BADGE, bg=C_BG, fg=C_JARVIS).pack(anchor=tk.W, pady=(2,0))
    tk.Label(left, text=f"☁  {GROQ_MODEL}",    font=FNT_BADGE, bg=C_BG, fg=C_FRIDAY).pack(anchor=tk.W, pady=(0,2))
    tk.Label(left, text=f"👁  {VISION_MODEL}",  font=FNT_BADGE, bg=C_BG, fg=C_FRIDAY).pack(anchor=tk.W, pady=(0,10))

    tk.Label(left, text="BATTERY", font=FNT_SUB, bg=C_BG, fg=C_DIM_TXT).pack(anchor=tk.W)
    bat_var = tk.StringVar(value="-- %")
    tk.Label(left, textvariable=bat_var, font=FNT_STATUS, bg=C_BG, fg=C_TEXT).pack(anchor=tk.W, pady=(2,0))

    # Right panel — conversation log
    right = tk.Frame(body, bg=C_BG)
    right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16,0))

    tk.Label(right, text="CONVERSATION LOG", font=FNT_SUB, bg=C_BG, fg=C_DIM_TXT).pack(anchor=tk.W)

    log_wrap = tk.Frame(right, bg=C_PANEL, highlightthickness=1, highlightbackground=C_DIM_TXT)
    log_wrap.pack(fill=tk.BOTH, expand=True, pady=(4,8))

    log = tk.Text(log_wrap, bg=C_PANEL, fg=C_TEXT, font=FNT_LOG,
                  wrap=tk.WORD, state=tk.DISABLED, cursor="arrow",
                  padx=10, pady=8, relief=tk.FLAT, selectbackground=C_DIM)
    log.pack(fill=tk.BOTH, expand=True)
    log.tag_config("user",   foreground=C_GOLD)
    log.tag_config("jarvis", foreground=C_JARVIS)
    log.tag_config("friday", foreground=C_FRIDAY)
    log.tag_config("sys",    foreground=C_DIM_TXT)

    tk.Label(right, text="LAST COMMAND", font=FNT_SUB, bg=C_BG, fg=C_DIM_TXT).pack(anchor=tk.W)
    cmd_var = tk.StringVar(value="—")
    tk.Label(right, textvariable=cmd_var, font=FNT_LOG,
             bg=C_BG, fg=C_TEXT, wraplength=600, justify=tk.LEFT).pack(anchor=tk.W)

    def append_log(msg, tag="sys"):
        log.config(state=tk.NORMAL)
        log.insert(tk.END, msg+"\n", tag)
        log.see(tk.END)
        log.config(state=tk.DISABLED)

    append_log("[ DUAL ASSISTANT ONLINE ]", "sys")
    append_log(f"[ Jarvis: {OLLAMA_MODEL}  |  Friday: {GROQ_MODEL} ]", "sys")
    append_log(f"[ Vision: {VISION_MODEL} ]", "sys")
    append_log(f"[ Wake: '{WAKE_JARVIS_KW}' → Jarvis  |  '{WAKE_FRIDAY_KW}' → Friday ]", "sys")
    append_log("─" * 56, "sys")

    # Visualizer
    NUM_BARS = 18
    bar_w, gap = 8, 3
    total_w = NUM_BARS * (bar_w + gap)
    ox = (210 - total_w) // 2
    bars = []
    for i in range(NUM_BARS):
        x = ox + i * (bar_w + gap)
        bars.append(vis.create_rectangle(x, 60, x+bar_w, 60, fill=C_DIM, outline=""))

    _phase = [0.0]

    def update_vis():
        _phase[0] += 0.18
        s     = ui_state
        asst  = active_assistant
        color = C_FRIDAY if asst == "friday" else C_JARVIS
        for i, bid in enumerate(bars):
            x = ox + i * (bar_w + gap)
            if s == State.LISTENING:
                wave = math.sin(_phase[0] + i * 0.55) * 0.5 + 0.5
                h    = int((wave + random.uniform(0, 0.4)) * 48) + 8
            elif s == State.SPEAKING:
                wave = math.sin(_phase[0] * 1.4 + i * 0.45) * 0.5 + 0.5
                h    = int(wave * 34) + 6
            elif s == State.THINKING:
                wave  = math.sin(_phase[0] * 0.6 + i * 0.3) * 0.5 + 0.5
                h     = int(wave * 20) + 4
                color = C_GOLD
            else:
                h = random.randint(2, 5); color = C_DIM_TXT
            vis.coords(bid, x, 60-h, x+bar_w, 60+h)
            vis.itemconfig(bid, fill=color)
        root.after(55, update_vis)

    _prev = {"heard": "", "reply": ""}

    def poll():
        asst = active_assistant
        active_var.set(f"● {'FRIDAY' if asst=='friday' else 'JARVIS'}")
        active_lbl.config(fg=C_FRIDAY if asst=="friday" else C_JARVIS)

        s = ui_state
        cfg = {
            State.LISTENING: ("● LISTENING", C_FRIDAY if asst=="friday" else C_JARVIS),
            State.SPEAKING:  ("● SPEAKING",  C_GREEN),
            State.THINKING:  ("● THINKING",  C_GOLD),
            State.IDLE:      ("● STANDBY",   C_DIM_TXT),
        }
        lbl, col = cfg.get(s, ("● STANDBY", C_DIM_TXT))
        state_var.set(lbl); state_lbl.config(fg=col)

        if last_heard and last_heard != _prev["heard"]:
            _prev["heard"] = last_heard
            cmd_var.set(last_heard)
            append_log(f"YOU   ▶  {last_heard}", "user")

        if last_reply and last_reply != _prev["reply"]:
            _prev["reply"] = last_reply
            who = last_who or "jarvis"
            prefix = "FRI   ▶" if who == "friday" else "JAR   ▶"
            append_log(f"{prefix}  {last_reply}", who)

        clock_var.set(datetime.datetime.now().strftime("%H:%M:%S  |  %a %d %b %Y"))

        try:
            b = psutil.sensors_battery()
            if b: bat_var.set(f"{'⚡' if b.power_plugged else '🔋'} {int(b.percent)}%")
        except: pass

        root.after(300, poll)

    update_vis()
    poll()
    root.mainloop()

# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=audio_loop, daemon=True).start()
    run_ui()