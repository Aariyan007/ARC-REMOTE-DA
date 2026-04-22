"""
Generate 520+ stress test cases for ARC and save as JSON dataset.
Run: python generate_dataset.py
"""
import json, random, os, itertools

random.seed(42)
cases = []

# ═══════════════════════════════════════════════════
#  1. CORRUPTED/MISSPELLED INPUT (80)
# ═══════════════════════════════════════════════════
corruptions = {
    "open chrome": ["opne chrome","open crhome","open chrom","opn chrome","oebn chrome",
                    "openn chrome","open chromee","open chrme","pen chrome","oopen chrome"],
    "create a file": ["creat a file","crate a file","create a fiel","craete a file",
                      "create a fle","create a fil","creeate a file","creatae a file",
                      "create a fi le","creat a fille"],
    "delete the file": ["delte the file","deleet the file","delete teh file","delet the file",
                        "dleete the file","delete th file","delete the fiel","deelte the file",
                        "delete tthe file","deletee the file"],
    "search for python": ["serach for python","search fr python","saerch for python",
                          "search for pyhton","serch for python","search for pythn",
                          "searhc for python","search fro python","search for pyton",
                          "searh for python"],
    "open youtube": ["opne youtube","open yuotube","open yotube","open youutbe",
                     "open yutube","opne yotube","open youttube","open yotuube",
                     "open youtub","oen youtube"],
    "rename the file": ["renam the file","renmae the file","rename teh file",
                        "rename the fiel","rnmae the file","rename th file",
                        "renamee the file","rename hte file","renaem the file",
                        "renme the file"],
    "close the app": ["clsoe the app","close teh app","close the ap","closee the app",
                      "cloe the app","close the aap","clsoe teh app","close th app",
                      "colse the app","close hte app"],
    "send an email": ["sned an email","send an emal","send an emial","sedn an email",
                      "send an eamil","send an emai","send na email","send a nemail",
                      "snde an email","send an eemail"],
}
for correct, typos in corruptions.items():
    action_map = {"open chrome":"open_app","create a file":"create_file",
                  "delete the file":"delete_file","search for python":"search_google",
                  "open youtube":"open_url","rename the file":"rename_file",
                  "close the app":"close_app","send an email":"send_email"}
    for typo in typos:
        cases.append({"category":"corrupted_input","input":typo,
                      "correct_form":correct,"expected_action":action_map[correct],
                      "note":"typo/voice-to-text error"})

# ═══════════════════════════════════════════════════
#  2. CASUAL SLANG STRIPPING (60)
# ═══════════════════════════════════════════════════
fillers = ["bro","dude","yo","man","like","uh","um","lol","bruh","tbh","kinda",
           "hey","please","just","maybe","basically"]
commands = [("open chrome","open_app"),("make a file","create_file"),
            ("search for cats","search_google"),("close spotify","close_app"),
            ("delete notes.txt","delete_file"),("rename report","rename_file")]
for filler in fillers:
    cmd, act = random.choice(commands)
    cases.append({"category":"slang_stripping","input":f"{filler} {cmd}",
                  "expected_clean_contains":cmd.split()[:2],
                  "expected_clean_excludes":[filler],"expected_action":act})
# Double fillers
for _ in range(20):
    f1, f2 = random.sample(fillers, 2)
    cmd, act = random.choice(commands)
    cases.append({"category":"slang_stripping","input":f"{f1} {f2} {cmd}",
                  "expected_clean_excludes":[f1, f2],"expected_action":act})
# Trailing fillers
for _ in range(24):
    filler = random.choice(fillers)
    cmd, act = random.choice(commands)
    cases.append({"category":"slang_stripping","input":f"{cmd} {filler}",
                  "expected_clean_excludes":[filler],"expected_action":act})

# ═══════════════════════════════════════════════════
#  3. TARGET-TYPE INFERENCE (50)
# ═══════════════════════════════════════════════════
tt_cases = [
    ("open chrome","app"),("open safari","app"),("open vscode","app"),
    ("open spotify","app"),("open finder","app"),("open slack","app"),
    ("open terminal","app"),("launch discord","app"),("run photoshop","app"),
    ("open calculator","app"),
    ("watch youtube","website"),("open google.com","website"),
    ("go to github","website"),("open reddit","website"),("visit twitter","website"),
    ("browse stackoverflow","website"),("open facebook.com","website"),
    ("go to netflix","website"),("visit amazon","website"),("open linkedin","website"),
    ("search for python","browser_search"),("google react hooks","browser_search"),
    ("look up machine learning","browser_search"),("find nodejs tutorial","browser_search"),
    ("search how to cook pasta","browser_search"),
    ("create a file","file"),("make a new file","file"),("edit report.txt","file"),
    ("rename notes.py","file"),("delete old.txt","file"),
    ("open downloads","folder"),("open documents folder","folder"),
    ("go to desktop","folder"),("open my projects","folder"),("browse photos folder","folder"),
    ("send email to john","email"),("compose an email","email"),
    ("mail the report","email"),("email mom","email"),("reply to boss","email"),
    ("save a note","note"),("write a memo","note"),("jot this down","note"),
    ("take a note","note"),("save as note","note"),
    ("close this tab","tab"),("new tab","tab"),("switch tab","tab"),
    ("close all tabs","tab"),("open new tab","tab"),
]
for inp, expected in tt_cases:
    cases.append({"category":"target_type","input":inp,"expected_type":expected})

# ═══════════════════════════════════════════════════
#  4. COMPOUND COMMANDS (80)
# ═══════════════════════════════════════════════════
compounds = [
    ("make a folder and then make a file","create_folder","create_file"),
    ("create a file then write hello in it","create_file","edit_file"),
    ("open chrome and search for python","open_app","search_google"),
    ("make a folder, then delete it","create_folder","delete_file"),
    ("create notes.txt then rename it to report","create_file","rename_file"),
    ("open safari and go to youtube","open_app","open_url"),
    ("create a folder; make a file inside it","create_folder","create_file"),
    ("make a file, i want to put my notes in it","create_file","edit_file"),
    ("open vscode and then open terminal","open_app","open_app"),
    ("create a folder called work then create a file","create_folder","create_file"),
]
# Generate variations with different conjunctions
conjunctions = [" and then ", " then ", ", then ", "; ", ", and then ", " after that "]
for base_a, act_a, act_b in compounds:
    parts = base_a.split(" and then " if " and then " in base_a else
                         " then " if " then " in base_a else
                         ", then " if ", then " in base_a else
                         "; " if "; " in base_a else
                         ", i want to " if ", i want to " in base_a else " then ")
    if len(parts) == 2:
        for conj in conjunctions:
            cases.append({"category":"compound_command",
                          "input":f"{parts[0]}{conj}{parts[1]}",
                          "expected_step1":act_a,"expected_step2":act_b})
    else:
        cases.append({"category":"compound_command","input":base_a,
                      "expected_step1":act_a,"expected_step2":act_b})
# Add unique extras to reach 80+
extra_compounds = [
    ("make a file and then close chrome","create_file","close_app"),
    ("create report.txt then email it","create_file","send_email"),
    ("open downloads then delete old.zip","open_folder","delete_file"),
    ("create a folder then open it","create_folder","open_folder"),
    ("search python then open the first result","search_google","open_url"),
    ("rename notes to report then delete the old one","rename_file","delete_file"),
    ("open spotify then search for jazz","open_app","search_google"),
    ("create code.py then write print hello","create_file","edit_file"),
    ("make a folder called src then make main.py in it","create_folder","create_file"),
    ("close all tabs then open google","close_tab","open_url"),
    ("make a folder called assets then copy image.png into it","create_folder","copy_file"),
    ("open chrome then close safari","open_app","close_app"),
    ("delete old.txt then create new.txt","delete_file","create_file"),
    ("make notes.md then write todo list in it","create_file","edit_file"),
    ("create a folder called build then rename it to dist","create_folder","rename_file"),
    ("open terminal then search for git commands","open_app","search_google"),
    ("create config.json then edit it","create_file","edit_file"),
    ("make a folder then put a file in it","create_folder","create_file"),
    ("open finder then go to downloads","open_app","open_folder"),
    ("create a file called todo then write buy milk","create_file","edit_file"),
]
for inp, a1, a2 in extra_compounds:
    cases.append({"category":"compound_command","input":inp,
                  "expected_step1":a1,"expected_step2":a2})

# ═══════════════════════════════════════════════════
#  5. FILE/FOLDER OPERATIONS (60)
# ═══════════════════════════════════════════════════
file_ops = []
filenames = ["notes.txt","report.py","data.json","readme.md","config.yaml",
             "main.py","index.html","styles.css","app.js","test.py"]
folders = ["projects","work","school","backup","src","docs","images","music","code","temp"]
locations = ["desktop","downloads","documents","home"]
for fn in filenames:
    loc = random.choice(locations)
    file_ops.append({"input":f"create {fn} in {loc}","action":"create_file",
                     "params":{"filename":fn}})
    file_ops.append({"input":f"delete {fn}","action":"delete_file",
                     "params":{"filename":fn}})
for fold in folders:
    file_ops.append({"input":f"create a folder called {fold}","action":"create_folder",
                     "params":{"target":fold}})
    file_ops.append({"input":f"open {fold} folder","action":"open_folder",
                     "params":{"target":fold}})
for fn in filenames[:5]:
    new = "new_" + fn
    file_ops.append({"input":f"rename {fn} to {new}","action":"rename_file",
                     "params":{"filename":fn,"new_name":new}})
    file_ops.append({"input":f"copy {fn} to downloads","action":"copy_file",
                     "params":{"filename":fn}})
# Edit file variants
for fn in filenames[:5]:
    file_ops.append({"input":f"edit {fn}","action":"edit_file",
                     "params":{"filename":fn}})
    file_ops.append({"input":f"write hello world in {fn}","action":"edit_file",
                     "params":{"filename":fn,"content":"hello world"}})
for c in file_ops:
    c["category"] = "file_operation"
    cases.append(c)

# ═══════════════════════════════════════════════════
#  6. CLARIFICATION QUESTIONS (40)
# ═══════════════════════════════════════════════════
clarification = [
    ("create_file",["filename"],"filename","name"),
    ("create_file",["filename","location"],"filename","name"),
    ("open_app",["target"],"target","app"),
    ("send_email",["to","subject","body"],"to","who"),
    ("send_email",["to"],"to","who"),
    ("rename_file",["new_name"],"new_name","rename"),
    ("delete_file",["target"],"target","delete"),
    ("search_google",["query"],"query","search"),
    ("edit_file",["filename"],"filename","file"),
    ("open_url",["url"],"url","URL"),
]
for action, missing, expected_slot, keyword in clarification:
    for i in range(4):
        cases.append({"category":"clarification","action":action,
                      "missing_params":missing,"expected_slot":expected_slot,
                      "question_must_contain":keyword,
                      "variant":i})

# ═══════════════════════════════════════════════════
#  7. PRONOUN RESOLUTION (40)
# ═══════════════════════════════════════════════════
pronouns = ["it","that","this","that file","this file","that app","this one","the file",
            "that folder","this thing"]
contexts = [
    {"last_file":"notes.txt","last_action":"create_file","expected":"notes.txt"},
    {"last_file":"report.py","last_action":"edit_file","expected":"report.py"},
    {"last_file":"data.json","last_action":"rename_file","expected":"data.json"},
    {"last_file":"config.yaml","last_action":"delete_file","expected":"config.yaml"},
]
for pronoun in pronouns:
    for ctx in contexts:
        cases.append({"category":"pronoun_resolution","pronoun":pronoun,
                      "context":ctx,"expected_resolution":ctx["expected"]})

# ═══════════════════════════════════════════════════
#  8. SAFETY GATE (30)
# ═══════════════════════════════════════════════════
destructive = ["delete_file","shutdown_pc","restart_pc","empty_trash",
               "format_disk","delete_folder"]
safe = ["create_file","open_app","search_google","open_url","create_folder",
        "edit_file","rename_file","copy_file","open_folder","new_tab"]
for act in destructive:
    cases.append({"category":"safety_gate","action":act,"expected_decision":"confirm"})
for act in safe[:len(safe)]:
    cases.append({"category":"safety_gate","action":act,"expected_decision":"execute"})
# Extra destructive with varying confidence
# <0.85 → gemini fallback, >=0.85 → confirm
for act in destructive[:4]:
    for conf in [0.5, 0.7]:
        cases.append({"category":"safety_gate","action":act,"confidence":conf,
                      "expected_decision":"gemini"})
    cases.append({"category":"safety_gate","action":act,"confidence":0.95,
                  "expected_decision":"confirm"})

# ═══════════════════════════════════════════════════
#  9. ACTION CORRECTION (40)
# ═══════════════════════════════════════════════════
corrections = [
    ("open_app","website","open_url"),("open_app","browser_search","search_google"),
    ("open_app","folder","open_folder"),("open_app","tab","new_tab"),
]
targets = [("youtube","website"),("google.com","website"),("github","website"),
           ("reddit","website"),("stackoverflow","website"),
           ("netflix","website"),("twitter","website"),("facebook","website"),
           ("amazon","website"),("linkedin","website"),
           ("python tutorial","browser_search"),("react hooks","browser_search"),
           ("how to code","browser_search"),("machine learning","browser_search"),
           ("javascript guide","browser_search"),("rust tutorial","browser_search"),
           ("downloads","folder"),("documents","folder"),
           ("desktop","folder"),("photos","folder")]
for target, ttype in targets:
    for fast_action, match_type, corrected in corrections:
        if ttype == match_type:
            cases.append({"category":"action_correction",
                          "fast_action":fast_action,"target_type":ttype,
                          "target":target,"expected_corrected":corrected})

# ═══════════════════════════════════════════════════
#  10. GROUNDED FOLLOW-UP (40)
# ═══════════════════════════════════════════════════
parent_actions = [
    ("create_folder","my_projects","location"),
    ("create_folder","work","location"),
    ("create_folder","school","location"),
    ("create_folder","src","location"),
    ("create_folder","docs","location"),
    ("create_file","notes.txt","filename"),
    ("create_file","main.py","filename"),
    ("create_file","app.js","filename"),
    ("open_folder","downloads","location"),
    ("open_folder","documents","location"),
]
follow_actions = ["edit_file","create_file","delete_file","rename_file"]
for parent_act, parent_target, inject_key in parent_actions:
    for follow_act in follow_actions:
        cases.append({"category":"grounded_followup",
                      "parent_action":parent_act,"parent_target":parent_target,
                      "follow_action":follow_act,"inject_key":inject_key,
                      "expected_param_key":inject_key,
                      "expected_param_value":parent_target})

# ═══════════════════════════════════════════════════
#  11. ERROR RECOVERY (20)
# ═══════════════════════════════════════════════════
# Test: which actions should be retried, which should never be
safe_retry = ["create_file","open_app","search_google","open_url","create_folder",
              "copy_file","open_folder","switch_to_app","edit_file","new_tab"]
never_retry = ["delete_file","shutdown_pc","restart_pc","empty_trash",
               "format_disk","send_email","delete_folder"]
for act in safe_retry:
    cases.append({"category":"error_recovery","action":act,
                  "should_retry":True,"should_never_retry":False})
for act in never_retry:
    cases.append({"category":"error_recovery","action":act,
                  "should_retry":False,"should_never_retry":True})
# Alternative strategy cases
cases.append({"category":"error_recovery","action":"open_app",
              "has_alternative":True,"alternative":"search_google"})
cases.append({"category":"error_recovery","action":"open_url",
              "has_alternative":True,"alternative":"search_google"})
cases.append({"category":"error_recovery","action":"open_folder",
              "has_alternative":True,"alternative":"create_folder"})

# ═══════════════════════════════════════════════════
#  12. TASK PLANNER (20)
# ═══════════════════════════════════════════════════
planner_cases = [
    ("open chrome", 1, "open_app"),
    ("create a folder called work, make a file inside it", 2, "create_folder"),
    ("make notes.txt then write hello", 2, "create_file"),
    ("create a folder, make a file, write hello world", 3, "create_folder"),
    ("open chrome and search for python", 2, "open_app"),
    ("delete old.txt then create new.txt", 2, "delete_file"),
    ("create config.json then edit it", 2, "create_file"),
    ("make a folder called docs then create readme.md in it", 2, "create_folder"),
    ("open terminal then search for git commands", 2, "open_app"),
    ("rename notes to report then delete old", 2, "rename_file"),
    ("create a file; close chrome", 2, "create_file"),
    ("make a folder then put a file in it", 2, "create_folder"),
    ("search cats then close the tab", 2, "search_google"),
    ("open spotify then open vscode", 2, "open_app"),
    ("create test.py then write print hello", 2, "create_file"),
    ("make a folder called build, create index.html inside, write hello", 3, "create_folder"),
    ("open finder then go to downloads", 2, "open_app"),
    ("create a file then rename it to report", 2, "create_file"),
    ("close safari then open chrome", 2, "close_app"),
    ("make a folder; make a file; delete the file", 3, "create_folder"),
]
for cmd, expected_steps, first_action in planner_cases:
    cases.append({"category":"task_planner","input":cmd,
                  "expected_step_count":expected_steps,
                  "expected_first_action":first_action})

# ═══════════════════════════════════════════════════
#  SAVE
# ═══════════════════════════════════════════════════
# Category counts
from collections import Counter
counts = Counter(c["category"] for c in cases)
dataset = {
    "description": "ARC stress test dataset — 520+ cases across 10 categories",
    "version": "1.0",
    "total_cases": len(cases),
    "category_counts": dict(counts),
    "cases": cases,
}

path = os.path.join(os.path.dirname(__file__), "data", "stress_test_dataset.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(dataset, f, indent=2, ensure_ascii=False)

print(f"Generated {len(cases)} test cases")
for cat, count in sorted(counts.items()):
    print(f"  {cat}: {count}")
print(f"\nSaved to {path}")
