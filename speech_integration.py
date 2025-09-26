import asyncio
import json
import threading
import queue
import time
import sounddevice as sd
import numpy as np
import websockets
from openai import OpenAI
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SpeechIntegration:
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY in your .env file.")
        
        self.client = OpenAI(api_key=self.api_key)
        self.audio_queue = queue.Queue()
        self.response_queue = queue.Queue()
        self.is_listening = False
        self.is_speaking = False
        self.should_interrupt = False
        self.current_voice = "alloy"  # Default voice
        self.sample_rate = 24000  # OpenAI's expected sample rate
        self.ws_connection = None
        self.listen_thread = None
        self.speak_thread = None
        
        # Configure audio settings
        self.chunk_size = 4096
        self.audio_format = np.int16
        self.channels = 1
        
        print("[SpeechIntegration] Initialized successfully")
    
    def start_listening(self):
        """Start capturing audio from microphone"""
        if self.is_listening:
            return
        
        self.is_listening = True
        self.listen_thread = threading.Thread(target=self._listen_worker)
        self.listen_thread.daemon = True
        self.listen_thread.start()
        print("[SpeechIntegration] Started listening")
    
    def stop_listening(self):
        """Stop capturing audio from microphone"""
        self.is_listening = False
        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=1.0)
        print("[SpeechIntegration] Stopped listening")
    
    def _listen_worker(self):
        """Worker thread to capture audio from microphone"""
        try:
            with sd.InputStream(callback=self._audio_callback, 
                              channels=self.channels,
                              samplerate=self.sample_rate,
                              blocksize=self.chunk_size):
                print("[SpeechIntegration] Microphone stream started")
                while self.is_listening:
                    time.sleep(0.1)
        except Exception as e:
            print(f"[SpeechIntegration] Error in listen worker: {e}")
            self.is_listening = False
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback for audio data from microphone"""
        if status:
            print(f"[SpeechIntegration] Audio callback status: {status}")
        
        # Convert to the format expected by OpenAI
        audio_data = indata.copy()
        self.audio_queue.put(audio_data)
    
    async def process_audio(self):
        """Process audio using OpenAI's Realtime API"""
        try:
            # Connect to OpenAI's WebSocket endpoint
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with websockets.connect(
                "wss://api.openai.com/v1/audio/speech",
                extra_headers=headers
            ) as websocket:
                self.ws_connection = websocket
                
                # Send initial configuration
                await websocket.send(json.dumps({
                    "model": "whisper-1",
                    "encoding": "linear16",
                    "sample_rate": self.sample_rate
                }))
                
                # Process audio chunks
                while self.is_listening:
                    if not self.audio_queue.empty():
                        audio_chunk = self.audio_queue.get()
                        
                        # Send audio chunk
                        audio_bytes = audio_chunk.tobytes()
                        await websocket.send(audio_bytes)
                        
                        # Get response
                        response = await websocket.recv()
                        response_data = json.loads(response)
                        
                        if "text" in response_data and response_data["text"].strip():
                            self.response_queue.put(response_data["text"])
                    
                    await asyncio.sleep(0.1)
        
        except Exception as e:
            print(f"[SpeechIntegration] WebSocket error: {e}")
        finally:
            self.ws_connection = None
    
    def start_speech_processing(self):
        """Start the speech processing loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.process_audio())
    
    def get_speech_text(self):
        """Get transcribed text from the response queue"""
        if not self.response_queue.empty():
            return self.response_queue.get()
        return None
    
    def speak_text(self, text, voice=None):
        """Convert text to speech and play it"""
        if not text:
            return
        
        if voice:
            self.current_voice = voice
        
        self.is_speaking = True
        self.should_interrupt = False
        
        self.speak_thread = threading.Thread(target=self._speak_worker, args=(text,))
        self.speak_thread.daemon = True
        self.speak_thread.start()
    
    def _speak_worker(self, text):
        """Worker thread to handle text-to-speech conversion and playback"""
        try:
            response = self.client.audio.speech.create(
                model="tts-1",
                voice=self.current_voice,
                input=text
            )
            
            # Get audio data
            audio_data = response.content
            
            # Play audio if not interrupted
            if not self.should_interrupt:
                # Convert audio data to numpy array for playback
                import io
                import wave
                
                with io.BytesIO(audio_data) as audio_io:
                    with wave.open(audio_io, 'rb') as wave_file:
                        sample_rate = wave_file.getframerate()
                        num_channels = wave_file.getnchannels()
                        sample_width = wave_file.getsampwidth()
                        audio_data = wave_file.readframes(wave_file.getnframes())
                
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                
                # Play audio
                sd.play(audio_array, sample_rate)
                sd.wait()
        
        except Exception as e:
            print(f"[SpeechIntegration] Error in speak worker: {e}")
        finally:
            self.is_speaking = False
    
    def interrupt_speech(self):
        """Interrupt current speech playback"""
        if self.is_speaking:
            self.should_interrupt = True
            sd.stop()
            if self.speak_thread and self.speak_thread.is_alive():
                self.speak_thread.join(timeout=1.0)
            self.is_speaking = False
            print("[SpeechIntegration] Speech interrupted")
    
    def set_voice(self, voice):
        """Set the voice for text-to-speech"""
        valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        if voice in valid_voices:
            self.current_voice = voice
            print(f"[SpeechIntegration] Voice set to {voice}")
        else:
            print(f"[SpeechIntegration] Invalid voice: {voice}. Using default: {self.current_voice}")
    
    def cleanup(self):
        """Clean up resources"""
        self.stop_listening()
        self.interrupt_speech()
        print("[SpeechIntegration] Cleanup complete")