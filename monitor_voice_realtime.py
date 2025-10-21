#!/usr/bin/env python3
"""Real-Time Voice Assistant Monitor

This script provides a live visual display of:
- Audio levels (RMS)
- AGC gain
- VAD status
- Wake word detection
- Speech capture state

Run this alongside your voice assistant to see what's happening in real-time.
"""

import sys
import os
import time
import audioop
import numpy as np
import pyaudio
from collections import deque

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.audio.agc import AutomaticGainControl, AdaptiveVAD
from app.audio.stt import StreamingTranscriber
from app.util.config import load_config


class VoiceMonitor:
    """Real-time voice assistant monitor with visual display"""
    
    def __init__(self, config):
        self.config = config
        self.SAMPLE_RATE = 16000
        self.CHUNK_SIZE = 4096
        
        # Initialize components
        self.agc = AutomaticGainControl(
            target_rms=3000.0,
            min_gain=1.0,
            max_gain=10.0
        )
        
        self.adaptive_vad = AdaptiveVAD(sample_rate=self.SAMPLE_RATE)
        
        self.stt = StreamingTranscriber(
            model_path=config.vosk_model_path,
            sample_rate=self.SAMPLE_RATE
        )
        self.stt.start()
        
        # Stats tracking
        self.rms_history = deque(maxlen=50)
        self.gain_history = deque(maxlen=50)
        self.wake_detections = []
        self.speech_events = []
        
        # State
        self.is_speech = False
        self.last_text = ""
        
    def clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def draw_bar(self, value: float, max_value: float, width: int = 40) -> str:
        """Draw a visual bar graph"""
        filled = int((value / max_value) * width)
        filled = max(0, min(width, filled))
        return "█" * filled + "░" * (width - filled)
    
    def draw_meter(self, value: float, min_val: float, max_val: float, width: int = 40) -> str:
        """Draw a meter with min/max range"""
        normalized = (value - min_val) / (max_val - min_val)
        normalized = max(0.0, min(1.0, normalized))
        filled = int(normalized * width)
        return "█" * filled + "░" * (width - filled)
    
    def format_status(self, label: str, value: str, color: str = "white") -> str:
        """Format a status line with color"""
        colors = {
            "green": "\033[92m",
            "yellow": "\033[93m",
            "red": "\033[91m",
            "blue": "\033[94m",
            "white": "\033[97m",
            "reset": "\033[0m"
        }
        return f"{colors.get(color, colors['white'])}{label}: {value}{colors['reset']}"
    
    def display_frame(self, rms_before: int, rms_after: int, agc_stats: dict, 
                     vad_speech: bool, text: str):
        """Display current frame stats"""
        self.clear_screen()
        
        print("="*70)
        print(" "*20 + "VOICE ASSISTANT MONITOR")
        print("="*70)
        print()
        
        # Audio Levels
        print("┌─ AUDIO LEVELS " + "─"*54 + "┐")
        print("│")
        
        # RMS Before AGC
        rms_bar = self.draw_bar(rms_before, 10000, 40)
        rms_status = "QUIET" if rms_before < 500 else ("GOOD" if rms_before < 5000 else "LOUD")
        rms_color = "red" if rms_before < 500 else ("green" if rms_before < 5000 else "yellow")
        print(f"│  RMS (before AGC): [{rms_bar}] {rms_before:5d}")
        print(f"│  Status: {self.format_status('', rms_status, rms_color)}")
        print("│")
        
        # RMS After AGC
        rms_after_bar = self.draw_bar(rms_after, 10000, 40)
        target_diff = abs(rms_after - 3000)
        agc_status = "ON TARGET" if target_diff < 500 else "ADJUSTING"
        agc_color = "green" if target_diff < 500 else "yellow"
        print(f"│  RMS (after AGC):  [{rms_after_bar}] {rms_after:5d}")
        print(f"│  Status: {self.format_status('', agc_status, agc_color)}")
        print("│")
        print("└" + "─"*68 + "┘")
        print()
        
        # AGC Stats
        print("┌─ AGC (AUTOMATIC GAIN CONTROL) " + "─"*37 + "┐")
        print("│")
        
        gain = agc_stats['current_gain']
        gain_db = agc_stats['current_gain_db']
        gain_bar = self.draw_meter(gain, 1.0, 10.0, 40)
        gain_status = "NO BOOST" if gain < 1.5 else ("MODERATE" if gain < 5.0 else "HEAVY")
        gain_color = "green" if gain < 1.5 else ("yellow" if gain < 5.0 else "red")
        
        print(f"│  Gain:   [{gain_bar}] {gain:.2f}x ({gain_db:+.1f}dB)")
        print(f"│  Status: {self.format_status('', gain_status, gain_color)}")
        print(f"│  Target RMS: {agc_stats['target_rms']:.0f}")
        print(f"│  Current RMS: {agc_stats['running_rms']:.0f}")
        print("│")
        print("└" + "─"*68 + "┘")
        print()
        
        # VAD Status
        print("┌─ VAD (VOICE ACTIVITY DETECTION) " + "─"*34 + "┐")
        print("│")
        
        vad_status = "SPEECH DETECTED" if vad_speech else "SILENCE"
        vad_color = "green" if vad_speech else "white"
        vad_indicator = "●" if vad_speech else "○"
        vad_level = self.adaptive_vad.get_vad_level()
        
        print(f"│  Status: {self.format_status(vad_indicator, vad_status, vad_color)}")
        print(f"│  VAD Level: {vad_level} (auto-selected)")
        print("│")
        print("└" + "─"*68 + "┘")
        print()
        
        # Transcription
        print("┌─ TRANSCRIPTION " + "─"*51 + "┐")
        print("│")
        
        if text:
            # Truncate if too long
            display_text = text[:60] + "..." if len(text) > 60 else text
            print(f"│  {display_text}")
        else:
            print("│  (listening...)")
        
        print("│")
        print("└" + "─"*68 + "┘")
        print()
        
        # Wake Word Detections
        if self.wake_detections:
            recent = self.wake_detections[-3:]
            print("┌─ RECENT WAKE WORD DETECTIONS " + "─"*37 + "┐")
            print("│")
            for detection in recent:
                elapsed = detection['time']
                text = detection['text'][:50]
                print(f"│  [{elapsed:6.1f}s] {text}")
            print("│")
            print("└" + "─"*68 + "┘")
            print()
        
        # Instructions
        print("─"*70)
        print("Press Ctrl+C to stop monitoring")
        print("─"*70)
    
    def run(self):
        """Run the monitor"""
        print("Starting Voice Assistant Monitor...")
        print("Initializing audio stream...")
        
        p = pyaudio.PyAudio()
        
        # Get default input device
        default_device = p.get_default_input_device_info()
        print(f"Using: {default_device['name']}")
        
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.SAMPLE_RATE,
            input=True,
            frames_per_buffer=self.CHUNK_SIZE,
            start=True
        )
        
        print("Monitor started! Speak to see real-time stats...")
        time.sleep(2)
        
        start_time = time.time()
        wake_words = ["hey glasses", "hi glasses", "ok glasses"]
        
        try:
            while True:
                # Read audio
                raw_chunk = stream.read(self.CHUNK_SIZE, exception_on_overflow=False)
                
                # Get RMS before AGC
                rms_before = audioop.rms(raw_chunk, 2)
                
                # Apply AGC
                gained_chunk = self.agc.process(raw_chunk)
                rms_after = audioop.rms(gained_chunk, 2)
                
                # Get AGC stats
                agc_stats = self.agc.get_stats()
                
                # Check VAD
                vad_speech = self.adaptive_vad.is_speech(gained_chunk)
                
                # Feed to STT
                self.stt.feed(gained_chunk)
                text = self.stt.combined_text
                
                # Check for wake word
                if text and text != self.last_text:
                    for wake_word in wake_words:
                        if wake_word in text.lower():
                            elapsed = time.time() - start_time
                            self.wake_detections.append({
                                'time': elapsed,
                                'text': text,
                                'rms_before': rms_before,
                                'rms_after': rms_after,
                                'gain': agc_stats['current_gain']
                            })
                            # Reset STT to avoid duplicate detections
                            self.stt.reset()
                            self.stt.start()
                            text = ""
                            break
                
                self.last_text = text
                
                # Track history
                self.rms_history.append(rms_after)
                self.gain_history.append(agc_stats['current_gain'])
                
                # Display
                self.display_frame(rms_before, rms_after, agc_stats, vad_speech, text)
                
                # Small delay to make display readable
                time.sleep(0.05)
                
        except KeyboardInterrupt:
            print("\n\nMonitor stopped.")
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            # Print summary
            if self.rms_history:
                print("\n" + "="*70)
                print("SESSION SUMMARY")
                print("="*70)
                print(f"Average RMS: {np.mean(self.rms_history):.0f}")
                print(f"Average Gain: {np.mean(self.gain_history):.2f}x")
                print(f"Wake Word Detections: {len(self.wake_detections)}")
                print("="*70 + "\n")


def main():
    """Main entry point"""
    print("\n" + "="*70)
    print(" "*15 + "VOICE ASSISTANT REAL-TIME MONITOR")
    print("="*70)
    print("\nThis tool shows real-time stats while you speak:")
    print("  • Audio levels (before/after AGC)")
    print("  • AGC gain and status")
    print("  • VAD speech detection")
    print("  • Live transcription")
    print("  • Wake word detections")
    print("\n" + "="*70 + "\n")
    
    try:
        # Load config
        config = load_config()
        print(f"✓ Config loaded: {config.vosk_model_path}\n")
        
        # Create and run monitor
        monitor = VoiceMonitor(config)
        
        input("Press Enter to start monitoring...")
        
        monitor.run()
        
    except KeyboardInterrupt:
        print("\n\nMonitor interrupted.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
