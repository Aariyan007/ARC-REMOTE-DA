import os

VAULT_PATH = "/Users/lynux/Desktop/Jarvis_Second_Brain"

# Define the real architecture of Jarvis
nodes = {
    "ManagerBrain": ["IntentRouter", "FileSystemAgent", "MusicAgent", "SystemControlAgent", "KnowledgeAgent", "Gemini_Pro"],
    "IntentRouter": ["FastIntent", "SafetySandbox", "SpeechToText", "InterruptManager"],
    "FastIntent": ["SentenceTransformers", "Intent_Registry"],
    "SpeechToText": ["Whisper_Model", "Microphone_Listener"],
    "KnowledgeAgent": ["Obsidian_Vault", "Markdown_Parser"],
    "FileSystemAgent": ["File_History_Memory", "OS_Operations"],
    "MusicAgent": ["Spotify_AppleScript", "Mood_to_Query_LLM"],
    "SystemControlAgent": ["osascript", "macOS_Control"],
    "SafetySandbox": ["Confirmation_Prompts", "Destructive_Commands_List"],
    "Gemini_Pro": ["Context_Resolution", "Complex_Planning"],
    "ElevenLabs": ["Voice_Response", "TTS_Engine"],
    "Whisper_Model": ["Local_Transcription", "Audio_Ducking"],
    "Spotify_AppleScript": ["play_track_URI", "mac_UI_automation_deprecated"],
    "InterruptManager": ["Exact_Match_Logic", "Voice_Cancellation"],
    "File_History_Memory": ["Pronoun_Resolution", "Last_Touched_File"],
    "Voice_Response": ["ElevenLabs", "MacOS_Say", "Instant_Acknowledgements"]
}

# Add nodes to different folders
folder_map = {
    "ManagerBrain": "1_Projects",
    "IntentRouter": "1_Projects",
    "Gemini_Pro": "3_Resources",
    "ElevenLabs": "3_Resources",
    "Whisper_Model": "3_Resources",
    "SentenceTransformers": "3_Resources",
    "Spotify_AppleScript": "2_Areas",
    "Obsidian_Vault": "2_Areas"
}

print(f"Populating real Jarvis architecture nodes into {VAULT_PATH}...")

for node, links in nodes.items():
    folder = folder_map.get(node, "1_Projects") # Default to Projects if not mapped
    path = os.path.join(VAULT_PATH, folder, f"{node}.md")
    
    content = f"# {node}\n\n"
    content += "Part of the Jarvis AI OS Architecture.\n\n"
    content += "### Connections\n"
    for link in links:
        content += f"- [[{link}]]\n"
        
        # Ensure the linked node exists structurally even if it doesn't have outgoing links
        if link not in nodes:
            linked_folder = folder_map.get(link, "2_Areas")
            linked_path = os.path.join(VAULT_PATH, linked_folder, f"{link}.md")
            if not os.path.exists(linked_path):
                with open(linked_path, "w") as f:
                    f.write(f"# {link}\n\nRelated to [[{node}]].\n")
            
    with open(path, "w") as f:
        f.write(content)

print(f"✅ Generated {len(nodes) + sum(len(v) for v in nodes.values())} highly interconnected, real architecture nodes!")
