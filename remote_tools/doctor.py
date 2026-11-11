"""
Diagnose file search on this machine.

    python -m remote_tools.doctor              # show folders ARC can see + file counts
    python -m remote_tools.doctor budget.xlsx  # also test a search and show where it looks

Folders come from ARC_FILE_ROOTS (default: ~/Desktop, ~/Documents, ~/Downloads).
To let ARC see more, set e.g. in .env:   ARC_FILE_ROOTS=/Users/you/Desktop:/Users/you/Projects
(separate folders with ':' on macOS/Linux, ';' on Windows).
"""

import os
import sys

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass

from remote_tools import files, policy


def main(argv):
    configured = os.getenv("ARC_FILE_ROOTS", "").strip()
    print("ARC_FILE_ROOTS:", configured or "(not set -> Desktop, Documents, Downloads)")
    roots = policy.file_roots()
    if not roots:
        print("\nNo usable folders! None of the configured folders exist.")
        return 1
    print("\nFolders ARC can search:")
    stats = files.index_stats(roots)
    for r in roots:
        st = stats.get(r, {})
        flag = "  (TRUNCATED: too many files, part not searched)" if st.get("truncated") else ""
        if st.get("permission_denied"):
            flag += ("\n      !! PERMISSION DENIED reading part of this folder. On macOS open System Settings > "
                     "Privacy & Security > Files and Folders (or Full Disk Access) and allow your terminal / Python, "
                     "then restart.")
        print(f"  {r}  ->  {st.get('files', 0)} files{flag}")
    print("\nSkipped folder names:", ", ".join(sorted(files.SKIP_DIRS)), "+ anything starting with '.'")

    for q in argv:
        print(f"\nSearch for {q!r}:")
        res = files.find_files(q, roots=roots, limit=8)
        if not res["matches"]:
            print("  nothing found in the folders above.")
            print("  If the file is somewhere else, add that folder to ARC_FILE_ROOTS.")
            if os.path.isabs(q) or os.sep in q or q.startswith("~"):
                real = os.path.realpath(os.path.expanduser(q))
                print(f"  That path exists: {os.path.exists(real)}; inside an allowed folder: "
                      f"{policy.safe_file_path(real, roots) is not None}")
            continue
        print("  exact match" if res["exact"] else "  no exact match; similar names:")
        for m in res["matches"]:
            print(f"   - {m['path']}  [{m['match_type']}, {m['score']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
