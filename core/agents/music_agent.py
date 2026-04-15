"""
MusicAgent — handles music playback cross-platform via Spotify.

Capabilities:
- play_music, pause_music, next_track, previous_track
- play_playlist
- play_song: searches + plays a specific song, announces name & artist
- play_mood_music: asks mood, maps to genre, plays & announces

macOS: Uses AppleScript to control Spotify natively.
Windows: Uses media key simulation via ctypes + webbrowser for Spotify search.
"""

import subprocess
import sys
import os
import time
import random
from core.agents.base_agent import BaseAgent, AgentResult
from core.voice_response import speak
from core.speech_to_text import listen


class MusicAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "music"

    @property
    def description(self) -> str:
        return (
            "Controls music playback cross-platform via Spotify. "
            "Can play/pause, skip tracks, search songs by name, "
            "play mood-based music, and announce currently playing track."
        )

    def __init__(self):
        super().__init__()

        self.register_action("play_music",      self._play)
        self.register_action("pause_music",     self._pause)
        self.register_action("next_track",      self._next_track)
        self.register_action("previous_track",  self._previous_track)
        self.register_action("play_playlist",   self._play_playlist)
        self.register_action("play_song",       self._play_song)
        self.register_action("play_mood_music", self._play_mood_music)

    # ─── macOS: AppleScript Helpers ──────────────────────────

    def _execute_applescript(self, script: str) -> str:
        """Helper to run AppleScript commands for Spotify."""
        full_script = f'''
        tell application "System Events"
            if not (exists process "Spotify") then
                return "Spotify is not running"
            end if
        end tell
        tell application "Spotify"
            {script}
        end tell
        '''
        try:
            result = subprocess.run(
                ["osascript", "-e", full_script],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() or "Success"
        except subprocess.TimeoutExpired:
            return "Command timed out"
        except Exception as e:
            return f"Error: {e}"

    def _ensure_spotify_running(self):
        """Launches Spotify if not already running (macOS)."""
        if sys.platform == "darwin":
            check = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to return (exists process "Spotify")'],
                capture_output=True, text=True, timeout=3
            )
            if "false" in check.stdout.lower():
                subprocess.Popen(["open", "-a", "Spotify"])
                print("🎵 Launching Spotify...")
                time.sleep(3)  # Give it time to start

    def _get_current_track(self) -> dict:
        """Gets the currently playing track info from Spotify (macOS)."""
        if sys.platform != "darwin":
            return {"name": "Unknown", "artist": "Unknown"}
        try:
            script = '''
            tell application "Spotify"
                set trackName to name of current track
                set trackArtist to artist of current track
                set trackAlbum to album of current track
                return trackName & "|||" & trackArtist & "|||" & trackAlbum
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            parts = result.stdout.strip().split("|||")
            if len(parts) >= 2:
                return {
                    "name": parts[0].strip(),
                    "artist": parts[1].strip(),
                    "album": parts[2].strip() if len(parts) > 2 else "",
                }
        except Exception as e:
            print(f"⚠️  Track info error: {e}")
        return {"name": "Unknown", "artist": "Unknown"}

    def _announce_track(self):
        """Speaks the currently playing track name and artist."""
        time.sleep(2)  # Give Spotify a moment to start the track
        track = self._get_current_track()
        if track["name"] != "Unknown":
            speak(f"Playing {track['name']} by {track['artist']}")
            print(f"🎵 Now playing: {track['name']} by {track['artist']}")
        return track

    def _search_and_play(self, query: str) -> str:
        """Searches Spotify for a query and plays the first result."""
        import urllib.parse
        encoded = urllib.parse.quote(query)

        self._ensure_spotify_running()

        if sys.platform == "darwin":
            # Use the Spotify AppleScript 'play track' command with search URI.
            # This is native and avoids any UI scripting.
            script = f'''
            tell application "Spotify"
                play track "spotify:search:{encoded}"
            end tell
            '''
            try:
                subprocess.run(["osascript", "-e", script], timeout=5)
                time.sleep(1)
                track = self._get_current_track()
                if track["name"] != "Unknown":
                    return f"Playing {track['name']} by {track['artist']}"
                return f"Playing {query} on Spotify"
            except Exception as e:
                return f"Error searching: {e}"
        else:
            import webbrowser
            spotify_uri = f"spotify:search:{encoded}"
            webbrowser.open(spotify_uri)
            return f"Searching {query} on Spotify"

    def _mood_to_query(self, mood_text: str) -> str:
        """Uses Gemini to map a mood description to a Spotify search query."""
        try:
            from google import genai
            client = genai.Client(api_key=os.getenv("API_KEY"))
            prompt = f"""The user described their mood as: "{mood_text}"

Suggest ONE Spotify search query that would match this mood perfectly.
Return ONLY the search query, nothing else. No quotes. No explanation.
Examples:
- "happy" → upbeat pop hits
- "sad" → sad acoustic songs
- "focused" → lo-fi study beats
- "energetic" → workout hip hop
- "relaxed" → chill indie vibes
- "stressed" → calm piano music
- "party" → party dance hits 2024
- "romantic" → love songs R&B
"""
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            query = response.text.strip()
            print(f"🎵 Mood '{mood_text}' → Spotify query: '{query}'")
            return query
        except Exception as e:
            print(f"⚠️  Mood mapping failed: {e}")
            # Fallback mapping
            fallback = {
                "happy": "upbeat pop hits",
                "sad": "sad acoustic songs",
                "focused": "lo-fi study beats",
                "energetic": "workout hip hop",
                "relaxed": "chill indie vibes",
                "stressed": "calm piano music",
            }
            for key, val in fallback.items():
                if key in mood_text.lower():
                    return val
            return "trending hits 2024"

    # ─── Windows: Media Key Simulation ───────────────────────

    def _press_media_key(self, vk_code: int) -> str:
        """Simulate a media key press on Windows using ctypes."""
        try:
            import ctypes
            KEYEVENTF_EXTENDEDKEY = 0x0001
            KEYEVENTF_KEYUP      = 0x0002

            user32 = ctypes.windll.user32
            # Key down
            user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
            # Key up
            user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
            return "Success"
        except Exception as e:
            return f"Error: {e}"

    # ─── Cross-platform actions ──────────────────────────────

    def _play(self, params: dict) -> AgentResult:
        """Resumes playback."""
        self._ensure_spotify_running()
        if sys.platform == "darwin":
            res = self._execute_applescript("play")
        else:
            # VK_MEDIA_PLAY_PAUSE = 0xB3
            res = self._press_media_key(0xB3)
        self._announce_track()
        return AgentResult(success=("Error" not in res), action="play_music", result=res)

    def _pause(self, params: dict) -> AgentResult:
        """Pauses playback."""
        if sys.platform == "darwin":
            res = self._execute_applescript("pause")
        else:
            # VK_MEDIA_PLAY_PAUSE = 0xB3 (toggle)
            res = self._press_media_key(0xB3)
        return AgentResult(success=("Error" not in res), action="pause_music", result=res)

    def _next_track(self, params: dict) -> AgentResult:
        """Skips to the next track."""
        if sys.platform == "darwin":
            res = self._execute_applescript("next track")
        else:
            # VK_MEDIA_NEXT_TRACK = 0xB0
            res = self._press_media_key(0xB0)
        self._announce_track()
        return AgentResult(success=("Error" not in res), action="next_track", result=res)

    def _previous_track(self, params: dict) -> AgentResult:
        """Goes to the previous track."""
        if sys.platform == "darwin":
            res = self._execute_applescript("previous track")
        else:
            # VK_MEDIA_PREV_TRACK = 0xB1
            res = self._press_media_key(0xB1)
        self._announce_track()
        return AgentResult(success=("Error" not in res), action="previous_track", result=res)

    def _play_playlist(self, params: dict) -> AgentResult:
        """Searches and plays a playlist/artist on Spotify."""
        query = params.get("query", params.get("name", ""))
        if not query:
            return AgentResult(success=False, action="play_playlist", error="No playlist name provided")

        speak(f"Searching for {query} on Spotify.")
        result = self._search_and_play(query)
        return AgentResult(
            success=("Error" not in result),
            action="play_playlist",
            result=result,
            data={"query": query}
        )

    def _play_song(self, params: dict) -> AgentResult:
        """
        Plays a specific song by name on Spotify.
        If no song name provided, plays trending music.
        Announces song name and artist before playing.
        """
        song_name = params.get("query", params.get("name", params.get("song", "")))

        if not song_name:
            # No specific song — play trending
            speak("No song specified. Playing something trending.")
            result = self._search_and_play("trending hits 2024")
            return AgentResult(
                success=("Error" not in result),
                action="play_song",
                result=result,
                data={"query": "trending hits 2024"}
            )

        speak(f"Searching for {song_name} on Spotify.")
        result = self._search_and_play(song_name)
        return AgentResult(
            success=("Error" not in result),
            action="play_song",
            result=result,
            data={"song": song_name}
        )

    def _play_mood_music(self, params: dict) -> AgentResult:
        """
        Asks user how they're feeling, then plays mood-appropriate music.
        Uses dynamic, varied prompts — never the same question twice.
        """
        mood_text = params.get("mood", "")

        if not mood_text:
            # Ask the user how they're feeling with varied prompts
            mood_prompts = [
                "How are you feeling right now?",
                "What's the vibe today?",
                "What kind of energy are you in?",
                "What mood should I match?",
                "Chill, energetic, or something else?",
                "Tell me your mood, I'll pick the music.",
                "What's the mood today, boss?",
                "Happy, focused, or need to unwind?",
            ]
            prompt = random.choice(mood_prompts)
            speak(prompt)
            mood_response = listen()
            if mood_response:
                mood_text = mood_response.strip()
            else:
                mood_text = "chill"
                speak("I'll go with something chill.")

        # Map mood to Spotify search query
        query = self._mood_to_query(mood_text)
        speak(f"Playing some {mood_text} vibes for you.")
        result = self._search_and_play(query)

        return AgentResult(
            success=("Error" not in result),
            action="play_mood_music",
            result=result,
            data={"mood": mood_text, "query": query}
        )

    def play_focus_music_silent(self):
        """
        Auto-plays focus music without asking — used when opening productive apps.
        No voice prompt, just plays and announces.
        """
        try:
            self._ensure_spotify_running()
            result = self._search_and_play("lo-fi study beats focus")
            time.sleep(2)
            track = self._get_current_track()
            if track["name"] != "Unknown":
                speak(f"Setting the mood. Playing {track['name']} by {track['artist']}.")
            return result
        except Exception as e:
            print(f"⚠️  Auto-play failed: {e}")
            return None


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    agent = MusicAgent()
    print("Testing MusicAgent...")
    print("Capabilities:", agent.capabilities)
    print(agent.execute("play_music", {}))
