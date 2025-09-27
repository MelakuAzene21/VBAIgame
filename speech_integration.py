import threading
import queue
import time
import speech_recognition as sr
import pyttsx3

class SpeechIntegration:
    def __init__(self):
        """Initialize the speech integration module with free alternatives."""
        print("[SpeechIntegration] Initializing...")
        
        # Initialize speech recognition
        self.recognizer = sr.Recognizer()
        self.microphone = None
        self.is_listening = False
        self.response_queue = queue.Queue()
        self.audio_queue = queue.Queue()  # Add audio_queue for compatibility
        self.listen_thread = None
        
        # Initialize text-to-speech
        self.engine = pyttsx3.init()
        self.is_speaking = False
        self.should_interrupt = False
        self.speak_thread = None
        
        # Set default voice properties
        self.current_voice = "alloy"  # Default voice
        
        # Get available voices
        self.available_voices = {}
        voices = self.engine.getProperty('voices')
        for voice in voices:
            self.available_voices[voice.id] = voice
            
        print("[SpeechIntegration] Initialized successfully")
        
    def set_voice(self, voice):
        """Set the voice for text-to-speech"""
        voice_mapping = {
            "alloy": 0,
            "echo": 0,
            "fable": 0,
            "onyx": 0,
            "nova": 1,
            "shimmer": 1
        }
        
        voices = self.engine.getProperty('voices')
        
        if voice in voice_mapping and len(voices) > voice_mapping[voice]:
            voice_index = voice_mapping[voice]
            self.engine.setProperty('voice', voices[voice_index].id)
            self.current_voice = voice
            print(f"[SpeechIntegration] Voice set to {voice}")
        else:
            print(f"[SpeechIntegration] Invalid voice: {voice}. Using default: {self.current_voice}")
        
    def start_listening(self):
        """Start capturing audio from microphone"""
        if self.is_listening:
            return
            
        print("[SpeechIntegration] Started listening")
        self.is_listening = True
        self.listen_thread = threading.Thread(target=self._listen_worker)
        self.listen_thread.daemon = True
        self.listen_thread.start()
        
    def stop_listening(self):
        """Stop capturing audio from microphone"""
        self.is_listening = False
        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=1.0)
        print("[SpeechIntegration] Stopped listening")
            
    def _listen_worker(self):
        """Worker thread for continuous speech recognition."""
        try:
            with sr.Microphone() as source:
                print("[SpeechIntegration] Microphone stream started")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                while self.is_listening:
                    try:
                        audio = self.recognizer.listen(source, timeout=1.0, phrase_time_limit=10.0)
                        
                        try:
                            text = self.recognizer.recognize_google(audio)
                            if text:
                                self.response_queue.put(text)
                        except sr.UnknownValueError:
                            pass  # Speech was unintelligible
                        except sr.RequestError as e:
                            print(f"[SpeechIntegration] Recognition error: {e}")
                            
                    except sr.WaitTimeoutError:
                        pass  # No speech detected within timeout
                        
        except Exception as e:
            print(f"[SpeechIntegration] Error in listen worker: {e}")
            self.is_listening = False
    
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
            self.set_voice(voice)

        # Reset flags every time
        self.should_interrupt = False
        self.is_speaking = True

        # Always create a new thread for speaking
        self.speak_thread = threading.Thread(target=self._speak_worker, args=(text,))
        self.speak_thread.daemon = True
        self.speak_thread.start()
        
    def _speak_worker(self, text):
        """Worker thread for text-to-speech (full text)."""
        try:
            if not self.should_interrupt:
                self.engine.say(text)
                self.engine.runAndWait()
        except Exception as e:
            print(f"[SpeechIntegration] Error in speak worker: {e}")
        finally:
            # Reset to allow next speech
            self.is_speaking = False
            self.should_interrupt = False
            
    def interrupt_speech(self):
        """Interrupt current speech playback"""
        if self.is_speaking:
            self.should_interrupt = True
            self.engine.stop()
            if self.speak_thread and self.speak_thread.is_alive():
                self.speak_thread.join(timeout=1.0)
            self.is_speaking = False
            print("[SpeechIntegration] Speech interrupted")
    
    def cleanup(self):
        """Clean up resources"""
        self.stop_listening()
        self.interrupt_speech()
        print("[SpeechIntegration] Cleanup complete")
