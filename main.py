import speech_recognition as sr
import edge_tts
import asyncio
import sounddevice as sd
import soundfile as sf
import io
import requests
import webbrowser
import threading
import json
from openai import OpenAI
from datetime import datetime
import time
import os
import pygame
from gtts import gTTS
from urllib.parse import quote


# =========================
# CONFIG
# =========================

ai_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"   # Can be any non-empty string
)

AI_MODEL = "qwen3:8b"   # or "gemma3:4b"


VOICE          = "en-IN-PrabhatNeural"
WS_PORT        = 6789                          # WebSocket port for the UI

# =========================
# EVENT LOOP (single persistent loop)
# =========================

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# =========================
# WEBSOCKET BROADCAST
# =========================

connected_clients = set()

async def ws_handler(websocket):
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)

def broadcast(msg: dict):
    """Send a JSON message to all connected browser clients."""
    if not connected_clients:
        return
    data = json.dumps(msg)
    async def _send():
        dead = set()
        for ws in connected_clients:
            try:
                await ws.send(data)
            except Exception:
                dead.add(ws)
        connected_clients.difference_update(dead)
    asyncio.run_coroutine_threadsafe(_send(), loop)

def ui_state(state: str, sub: str = ""):
    """Broadcast a state change (standby / wake / active / thinking / mute)."""
    broadcast({"type": "state", "state": state, "sub": sub})

def ui_log(kind: str, text: str):
    """Broadcast a log line. kind: sys | heard | cmd | jarvis | wake | err"""
    broadcast({"type": "log", "kind": kind, "text": text})

async def _start_ws_server():
    import websockets
    async with websockets.serve(ws_handler, "localhost", WS_PORT):
        await asyncio.Future()  # run forever

def start_ws_thread():
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("[UI] 'websockets' not installed — run: pip install websockets")
        print("[UI] Jarvis will still work, just without the browser UI.")
        return
    t = threading.Thread(target=lambda: loop.run_until_complete(_start_ws_server()), daemon=True)
    t.start()
    print(f"[UI] WebSocket server started on ws://localhost:{WS_PORT}")
    print(f"[UI] Open jarvis_ui.html in your browser to see the HUD.")

# =========================
# SPEECH (edge-tts)
# =========================

async def _speak_async(text):
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save("jarvis_voice.mp3")

def speak(text):
    print(f"Jarvis: {text}")
    ui_log("jarvis", f"Jarvis: {text}")

    asyncio.run(_speak_async(text))

    if not pygame.mixer.get_init():
        pygame.mixer.init()

    pygame.mixer.music.load("jarvis_voice.mp3")
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

    pygame.mixer.music.unload()

    try:
        os.remove("jarvis_voice.mp3")
    except:
        pass


#   Google Text to Speech ⬇️  (Female Voice )

    # tts = gTTS(text=text, lang="en")
    # tts.save("tts.mp3")

    # if not pygame.mixer.get_init():
    #     pygame.mixer.init()

    # pygame.mixer.music.load("tts.mp3")
    # pygame.mixer.music.play()          

    # while pygame.mixer.music.get_busy():
    #     pygame.time.Clock().tick(10)

    # pygame.mixer.music.unload()
    # os.remove("tts.mp3")

    
    # try:
    #     future = asyncio.run_coroutine_threadsafe(_speak_async(text), loop)
    #     future.result()
    # except Exception as e:
    #     print(f"[Speech Error]: {e}")


# =========================
# AI FALLBACK (Local LLM)
# =========================

def ask_ai(question):
    try:
        response = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Jarvis, a smart AI assistant like the one from Iron Man. "
                        "Keep all responses short, spoken, and natural. "
                        "Never use markdown, lists, or emojis. "
                        "Always address the user as Boss."
                    )
                },
                {
                    "role": "user",
                    "content": question
                }
            ],
            max_tokens=500,
            temperature=0.7
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[Ollama Error]: {e}")
        return "I'm having trouble connecting to the local AI model, Boss. Please make sure Ollama is running."

# =========================
# LISTEN
# =========================

recognizer = sr.Recognizer()

def listen(timeout=5, phrase_limit=8):
    try:
        with sr.Microphone() as source:
            print("Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        text = recognizer.recognize_google(audio)
        print(f"[Heard]: {text}")
        return text
    except sr.UnknownValueError:
        print("[Could not understand audio]")
        ui_log("err", "[Could not understand audio]")
        return None
    except sr.WaitTimeoutError:
        print("[Listening timed out]")
        ui_log("err", "[Listening timed out]")
        return None
    except sr.RequestError as e:
        print(f"[Google Speech API error]: {e}")
        ui_log("err", f"[Google Speech API error]: {e}")
        return None
    except Exception as e:
        print(f"[Listen error]: {e}")
        ui_log("err", f"[Listen error]: {e}")
        return None

# =========================
# COMMAND PROCESSOR
# =========================

running = True

def processCommand(command):
    global running
    cmd = command.lower().strip()
    print(f"[Command]: {cmd}")
    ui_log("cmd", f"[Command]: {cmd}")
    ui_state("thinking", "PROCESSING...")


    if cmd.lower().startswith("open "):
        site = cmd.split(maxsplit=1)[1]
        speak(f"Opening {site}.")
        webbrowser.open(f"https://{site}.com")


    elif "time" in cmd:
        speak(f"The time is {datetime.now().strftime('%I:%M %p')}, Boss.")

    elif "date" in cmd:
        speak(f"Today is {datetime.now().strftime('%d %B %Y')}, Boss.")

    elif any(w in cmd for w in ["exit", "goodbye", "shut down", "stop jarvis"]):
        speak("Goodbye Boss. Shutting down.")
        ui_state("mute", "OFFLINE")
        running = False


    elif cmd.lower().startswith("play"):
        song = cmd[5:].strip()
        link = f"https://www.youtube.com/results?search_query={quote(song)}"
        webbrowser.open(link)


    else:
        speak("Let me think, Boss.")
        ui_state("thinking", "ASKING AI...")
        speak(ask_ai(command))

# =========================
# MAIN
# =========================

if __name__ == "__main__":
    start_ws_thread()
    speak("Initialising Jarvis.")

    while running:
        try:
            print("\n--- Waiting for wake word 'Jarvis' ---")
            ui_log("sys", "--- Waiting for wake word 'Jarvis' ---")
            ui_state("standby", "SAY · JARVIS")

            wake_text = listen(timeout=6, phrase_limit=4)

            if wake_text is None:
                continue

            ui_log("heard", f"[Heard]: {wake_text}")

            if "jarvis" in wake_text.lower():
                ui_state("wake", "WAKE WORD DETECTED")
                speak("Yes Boss?")
                ui_state("active", "AWAITING COMMAND")

                print("--- Listening for command ---")
                ui_log("sys", "--- Listening for command ---")

                command = listen(timeout=8, phrase_limit=12)

                if command is None:
                    speak("I didn't catch that Boss, please try again.")
                    continue

                ui_log("heard", f"[Heard]: {command}")
                processCommand(command)
                ui_state("standby", "SAY · JARVIS")

        except KeyboardInterrupt:
            speak("Shutting down. Goodbye Boss.")
            ui_state("mute", "OFFLINE")
            print("\n[Stopped by user]")
            break

        except Exception as e:
            print(f"[Unexpected error]: {e}")
            ui_log("err", f"[Error]: {e}")
            time.sleep(1)