"""
MusicAgent — handles Spotify playback via native macOS AppleScript.

Capabilities:
- play_music, pause_music, next_track, previous_track
- play_playlist

Uses `osascript` to directly control the macOS Spotify application.
Requires NO API keys or spotipy installations.
"""

import subprocess
from core.agents.base_agent import BaseAgent, AgentResult


class MusicAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "music"

    @property
    def description(self) -> str:
        return (
            "Controls Spotify playback natively on Mac. "
            "Can play/pause music, skip tracks, and play specific playlists or genres."
        )

    def __init__(self):
        super().__init__()
        
        self.register_action("play_music",     self._play)
        self.register_action("pause_music",    self._pause)
        self.register_action("next_track",     self._next_track)
        self.register_action("previous_track", self._previous_track)
        self.register_action("play_playlist",  self._play_playlist)

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

    def _play(self, params: dict) -> AgentResult:
        """Resumes playback."""
        res = self._execute_applescript("play")
        return AgentResult(success=("Error" not in res), action="play_music", result=res)

    def _pause(self, params: dict) -> AgentResult:
        """Pauses playback."""
        res = self._execute_applescript("pause")
        return AgentResult(success=("Error" not in res), action="pause_music", result=res)

    def _next_track(self, params: dict) -> AgentResult:
        """Skips to the next track."""
        res = self._execute_applescript("next track")
        return AgentResult(success=("Error" not in res), action="next_track", result=res)

    def _previous_track(self, params: dict) -> AgentResult:
        """Goes to the previous track."""
        res = self._execute_applescript("previous track")
        return AgentResult(success=("Error" not in res), action="previous_track", result=res)

    def _play_playlist(self, params: dict) -> AgentResult:
        """
        Attempts to search and play a playlist/artist based on text input.
        Because AppleScript on modern Spotify doesn't support direct URI search easily without OAuth,
        we can use UI scripting or `open spotify:search:query`.
        """
        query = params.get("query", params.get("name", ""))
        if not query:
            return AgentResult(success=False, action="play_playlist", error="No playlist name provided")
            
        # URL encode the query
        import urllib.parse
        encoded = urllib.parse.quote(query)
        
        # Opens Spotify and initiates a search. Then plays it.
        # This is a hacky but effective way to play a query via native Desktop app.
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


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    agent = MusicAgent()
    print("Testing MusicAgent...")
    print(agent.execute("play_music", {}))
