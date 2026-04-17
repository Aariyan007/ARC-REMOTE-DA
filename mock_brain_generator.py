import os
import random
import datetime

# Configuration
VAULT_NAME = "Jarvis_Second_Brain"
DESKTOP_PATH = os.path.expanduser("~/Desktop")
VAULT_PATH = os.path.join(DESKTOP_PATH, VAULT_NAME)

FOLDERS = ["1_Projects", "2_Areas", "3_Resources", "4_Archives", "Daily_Notes"]

# Mock data themes
TOPICS = [
    "Artificial Intelligence", "Machine Learning", "Neural Networks", "Voice Assistants",
    "Python Automation", "Startup Ideas", "Productivity", "Health and Fitness",
    "Diet Plan", "System Architecture", "API Design", "React Frontend", 
    "Database Optimization", "Cybersecurity", "Investment Strategies",
    "Book Summaries", "Meeting Notes", "Brainstorming", "UI/UX Design",
    "Marketing Plan", "User Retention", "Cloud Infrastructure"
]

PEOPLE = ["Alex", "Sarah", "Dr. Chen", "Mike", "Elena"]
TAGS = ["#idea", "#urgent", "#todo", "#research", "#reference", "#bug"]

def setup_vault():
    print(f"Creating vault at: {VAULT_PATH}")
    os.makedirs(VAULT_PATH, exist_ok=True)
    for folder in FOLDERS:
        os.makedirs(os.path.join(VAULT_PATH, folder), exist_ok=True)

def generate_notes(num_notes=80):
    notes_created = []
    
    # 1. Generate Core Topic Notes (Resources/Areas)
    for topic in TOPICS:
        folder = random.choice(["2_Areas", "3_Resources"])
        safe_topic = topic.replace(' ', '_').replace('/', '_')
        filename = f"{safe_topic}.md"
        path = os.path.join(VAULT_PATH, folder, filename)
        
        content = f"# {topic}\n\n"
        content += f"This is a core concept note about {topic}.\n\n"
        content += f"Tags: {random.choice(TAGS)}\n"
        
        with open(path, "w") as f:
            f.write(content)
        notes_created.append(safe_topic)

    # 2. Generate Daily Notes and Projects (interlinking them)
    for i in range(num_notes - len(TOPICS)):
        is_daily = random.random() > 0.5
        
        if is_daily:
            folder = "Daily_Notes"
            date = datetime.date.today() - datetime.timedelta(days=random.randint(0, 30))
            name = f"Daily_{date.strftime('%Y-%m-%d')}_{random.randint(100,999)}"
        else:
            folder = "1_Projects"
            name = f"Project_Alpha_{i}"
            
        filename = f"{name}.md"
        path = os.path.join(VAULT_PATH, folder, filename)
        
        # Pick 2-4 random existing notes to link to
        links = random.sample(notes_created, min(len(notes_created), random.randint(2, 5)))
        links_markdown = " ".join([f"[[{link}]]" for link in links])
        
        content = f"# {name}\n\n"
        content += f"Summary of activity. Met with {random.choice(PEOPLE)} regarding the following topics:\n\n"
        content += f"- Discussed {links_markdown}\n"
        content += f"- Action items related to [[{random.choice(notes_created)}]]\n\n"
        content += f"Tags: {random.choice(TAGS)}\n"
        
        with open(path, "w") as f:
            f.write(content)
        notes_created.append(name)
        
    print(f"✅ Generated {len(notes_created)} interconnected notes!")
    print(f"Vault ready at: {VAULT_PATH}")

if __name__ == "__main__":
    setup_vault()
    generate_notes(100)
