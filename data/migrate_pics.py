"""
Migrate profile pics from flat gender folders to category/gender structure.
Moves: profile_pics/female/stock_face_selfie_0001.jpg -> profile_pics/face_selfie/female/stock_face_selfie_0001.jpg
Run this ONCE after git pull to reorganize existing downloads.
"""
import os
import shutil
from pathlib import Path

PICS_DIR = Path(__file__).parent / "profile_pics"

CATEGORIES = [
    'face_selfie', 'full_body_lifestyle', 'aesthetic_artistic',
    'mirror_selfie_gym', 'back_view_silhouette', 'other_diverse', 'other_unique'
]

def migrate():
    moved = 0
    errors = 0
    
    for gender in ['female', 'male', 'neutral']:
        gender_dir = PICS_DIR / gender
        if not gender_dir.exists():
            continue
        
        files = list(gender_dir.iterdir())
        print(f"Processing {gender}/ — {len(files)} files")
        
        for f in files:
            if not f.is_file():
                continue
            
            # Extract category from filename: stock_{category}_{number}.jpg
            name = f.stem  # e.g. stock_face_selfie_0001
            
            # Find which category this belongs to
            target_cat = None
            for cat in CATEGORIES:
                if cat in name:
                    target_cat = cat
                    break
            
            if not target_cat:
                print(f"  SKIP (no category match): {f.name}")
                continue
            
            # Create target directory and move
            target_dir = PICS_DIR / target_cat / gender
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f.name
            
            if target_path.exists():
                print(f"  SKIP (exists): {f.name}")
                continue
            
            shutil.move(str(f), str(target_path))
            moved += 1
        
        # Remove empty gender dir
        remaining = list(gender_dir.iterdir()) if gender_dir.exists() else []
        if not remaining:
            gender_dir.rmdir()
            print(f"  Removed empty {gender}/")
    
    print(f"\nDone! Moved {moved} files.")
    
    # Show new structure
    print("\nNew structure:")
    if PICS_DIR.exists():
        for cat_dir in sorted(PICS_DIR.iterdir()):
            if cat_dir.is_dir():
                total = sum(1 for _ in cat_dir.rglob('*.jpg'))
                if total > 0:
                    print(f"  {cat_dir.name}/")
                    for gender_dir in sorted(cat_dir.iterdir()):
                        if gender_dir.is_dir():
                            count = sum(1 for _ in gender_dir.glob('*.jpg'))
                            if count > 0:
                                print(f"    {gender_dir.name}/  ({count} photos)")

if __name__ == '__main__':
    migrate()
