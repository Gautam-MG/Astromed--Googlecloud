import sys
sys.path.append(r'c:\Users\Manoj\Downloads\Anurag sir Project')
from knowledge_base import get_nakshatra_diseases

tests = [
    ("Ashwini", 1),
    ("Ashwini", 2),
    ("Kruthika", 1),
    ("Kruthika", 2),
    ("Kruthika", 4),
    ("Unknown", 1)
]

for name, pada in tests:
    diseases = get_nakshatra_diseases(name, pada)
    print(f"{name} Pada {pada}: {len(diseases)} diseases found. {diseases[:2]}")
