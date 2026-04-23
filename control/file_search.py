import os
import re
from typing import Optional, List, Tuple

def search_files_advanced_multiple(query: str, root_dir: str = None, top_k: int = 5) -> List[str]:
    """
    Searches the filesystem for a file matching the natural language query.
    Returns a list of the top_k best absolute paths.
    """
    if not root_dir:
        user_profile = os.environ.get('USERPROFILE', '')
        if user_profile:
            search_dirs = [
                os.path.join(user_profile, "Desktop"),
                os.path.join(user_profile, "Documents"),
                os.path.join(user_profile, "Downloads")
            ]
        else:
            search_dirs = ["C:\\"]
    else:
        search_dirs = [root_dir]

    query_lower = query.lower()
    ext_match = re.search(r'\.(\w+)$', query_lower)
    target_ext = ext_match.group(0) if ext_match else None
    
    base_query = query_lower.replace(target_ext, '') if target_ext else query_lower
    base_query = base_query.strip()

    matches: List[Tuple[int, str]] = []

    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
            
        for root, _, files in os.walk(search_dir):
            if any(part.startswith('.') or part in ('AppData', 'Windows', 'Program Files') for part in root.split(os.sep)):
                continue
                
            for file in files:
                file_lower = file.lower()
                name, ext = os.path.splitext(file_lower)
                score = 0
                
                if target_ext and ext != target_ext:
                    continue
                
                if base_query == name:
                    score += 100
                elif base_query in name:
                    score += 50
                elif all(word in name for word in base_query.split()):
                    score += 25
                
                if score > 0:
                    matches.append((score, os.path.join(root, file)))

    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches[:top_k]]
    return []

def search_files_advanced(query: str, root_dir: str = None) -> Optional[str]:
    """Returns the absolute path of the single best match."""
    results = search_files_advanced_multiple(query, root_dir, top_k=1)
    if results:
        print(f"🔍 Found best match for '{query}': {results[0]}")
        return results[0]
    print(f"⚠️ No matches found for '{query}'")
    return None
