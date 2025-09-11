import json
import os
from pathlib import Path

from bs4 import BeautifulSoup

def main():
    """
    Parses static/app.html to extract chord progressions and styles,
    then generates JSON files for cache warming.
    """
    # Project root is two levels up from this script's directory
    project_root = Path(__file__).parent.parent
    html_path = project_root / "static" / "app.html"
    output_dir = project_root / "data" / "pregenerated"

    print(f"Parsing {html_path}...")

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")
    except FileNotFoundError:
        print(f"Error: {html_path} not found.")
        return

    # Extract chord progressions
    prog_select = soup.find("select", {"id": "chord-progression"})
    if not prog_select:
        print("Error: Could not find chord progression select element.")
        return
    # Use the first 10 progressions as per the original requirement's spirit
    progressions = [option["value"] for option in prog_select.find_all("option")][:10]
    print(f"Found {len(progressions)} chord progressions to use.")

    # Extract styles
    style_select = soup.find("select", {"id": "music-style"})
    if not style_select:
        print("Error: Could not find music style select element.")
        return
    styles = [option.text for option in style_select.find_all("option")]
    print(f"Found {len(styles)} styles.")

    # Create output directory and clean it
    output_dir.mkdir(parents=True, exist_ok=True)
    for f in output_dir.glob("*.json"):
        os.remove(f)
    print(f"Cleaned output directory: {output_dir}")

    # Generate JSON files
    file_count = 0
    for prog_idx, prog in enumerate(progressions, 1):
        for style_idx, style in enumerate(styles, 1):
            for variation in range(1, 6):
                modified_style = f"{style}_v{variation}"

                data = {
                    "chord_progression": prog,
                    "style": modified_style
                }

                filename = output_dir / f"prog{prog_idx:02d}_style{style_idx:02d}_var{variation:02d}.json"

                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                file_count += 1

    print(f"Successfully generated {file_count} JSON files in {output_dir}")

if __name__ == "__main__":
    main()
