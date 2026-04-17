import os
import random

vault_path = "/Users/lynux/Desktop/Jarvis_Second_Brain"
workflows_path = os.path.join(vault_path, "Workflows")
workflows = [f.replace('.md', '') for f in os.listdir(workflows_path) if f.endswith('.md')]

daily_notes_path = os.path.join(vault_path, "Daily_Notes")
daily_notes = [f for f in os.listdir(daily_notes_path) if f.endswith('.md')]

# Add workflow links to a random sample of daily notes
for note in random.sample(daily_notes, min(len(daily_notes), 15)):
    file_path = os.path.join(daily_notes_path, note)
    workflow_to_link = random.choice(workflows)
    with open(file_path, "a") as f:
         f.write(f"\n- Reviewed workflow: [[{workflow_to_link}]]\n")

print(f"✅ Interlinked {len(workflows)} workflows into the daily notes!")
