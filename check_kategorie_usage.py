import os
import re


def find_kategorie_references(root_dir):
    """Findet alle Referenzen auf Kategoriefelder"""

    patterns = [
        r"\.ueberkategorie",
        r"\.produktgruppe",
        r"ueberkategorie=",
        r"produktgruppe=",
        r"ueberkategorie__",
        r"produktgruppe__",
        r"'ueberkategorie'",
        r'"ueberkategorie"',
        r"'produktgruppe'",
        r'"produktgruppe"',
    ]

    results = {
        'views': [],
        'templates': [],
        'models': []
    }

    for root, dirs, files in os.walk(root_dir):
        # Überspringe virtuelle Umgebungen und Migration-Dateien
        if '.venv' in root or 'migrations' in root or '__pycache__' in root:
            continue

        for file in files:
            if file.endswith(('.py', '.html')):
                filepath = os.path.join(root, file)

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()

                    for pattern in patterns:
                        if re.search(pattern, content):
                            file_type = 'templates' if file.endswith('.html') else 'views'
                            if not any(filepath in item for item in results[file_type]):
                                results[file_type].append(filepath)
                            break
                except:
                    pass

    return results


if __name__ == '__main__':
    results = find_kategorie_references('./billa')

    print("=" * 60)
    print("KATEGORIE-REFERENZEN GEFUNDEN")
    print("=" * 60)

    print("\n📄 VIEWS/PYTHON-DATEIEN:")
    for file in sorted(results['views']):
        print(f"  - {file}")

    print("\n🎨 TEMPLATES:")
    for file in sorted(results['templates']):
        print(f"  - {file}")

    print(f"\nGesamt: {len(results['views'])} Python-Dateien, {len(results['templates'])} Templates")