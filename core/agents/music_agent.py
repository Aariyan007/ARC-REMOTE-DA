"""
MusicAgent — handles music playback cross-platform.

Capabilities:
- play_music, pause_music, next_track, previous_track
- play_playlist

macOS: Uses AppleScript to control Spotify natively.
Windows: Uses media key simulation via ctypes + webbrowser for Spotify search.
"""

import subprocess
import sys
from core.agents.base_agent import BaseAgent, AgentResult


class MusicAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "music"

    @property
    def description(self) -> str:
        return (
            "Controls music playback cross-platform. "
            "Can play/pause music, skip tracks, and play specific playlists or genres."
        )

    def __init__(self):
        super().__init__()

        self.register_action("play_music",     self._play)
        self.register_action("pause_music",    self._pause)
        self.register_action("next_track",     self._next_track)
        self.register_action("previous_track", self._previous_track)
        self.register_action("play_playlist",  self._play_playlist)

    # ─── macOS: AppleScript ──────────────────────────────────

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
        if sys.platform == "darwin":
            res = self._execute_applescript("play")
        else:
            # VK_MEDIA_PLAY_PAUSE = 0xB3
            res = self._press_media_key(0xB3)
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
        return AgentResult(success=("Error" not in res), action="next_track", result=res)

    def _previous_track(self, params: dict) -> AgentResult:
        """Goes to the previous track."""
        if sys.platform == "darwin":
            res = self._execute_applescript("previous track")
        else:
            # VK_MEDIA_PREV_TRACK = 0xB1
            res = self._press_media_key(0xB1)
        return AgentResult(success=("Error" not in res), action="previous_track", result=res)

    def _play_playlist(self, params: dict) -> AgentResult:
        """
        Searches and plays a playlist/artist.
        macOS: AppleScript + Spotify URI
        Windows: Opens Spotify search URI via webbrowser
        """
        query = params.get("query", params.get("name", ""))
        if not query:
            return AgentResult(success=False, action="play_playlist", error="No playlist name provided")

        import urllib.parse
        encoded = urllib.parse.quote(query)

        if sys.platform == "darwin":
            script = f'''
            open location "spotify:search:{encoded}"
            delay 1
            tell application "System Events"
                tell process "Spotify"
                    keystroke tab
                    keystroke return
                end tell
            end tell
            '''
            try:
                subprocess.run(["osascript", "-e", script], timeout=5)
                return AgentResult(
                    success=True,
                    action="play_playlist",
                    result=f"Playing {query} on Spotify",
                    data={"query": query}
                )
            except Exception as e:
                return AgentResult(success=False, action="play_playlist", error=str(e))
        else:
            # Windows: open Spotify search URI via webbrowser
            import webbrowser
            try:
                spotify_uri = f"spotify:search:{encoded}"
                webbrowser.open(spotify_uri)
                return AgentResult(
                    success=True,
                    action="play_playlist",
                    result=f"Searching {query} on Spotify",
                    data={"query": query}
                )
            except Exception as e:
                # Fallback: open Spotify web player search
                web_url = f"https://open.spotify.com/search/{encoded}"
                webbrowser.open(web_url)
                return AgentResult(
                    success=True,
                    action="play_playlist",
                    result=f"Opened Spotify web search for {query}",
                    data={"query": query}
                )


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    agent = MusicAgent()
    print("Testing MusicAgent...")
    print(agent.execute("play_music", {}))
