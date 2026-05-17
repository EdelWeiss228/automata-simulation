import csv
import sys

def compare_csv(file1, file2):
    with open(file1, "r", encoding="utf-8") as f1, open(file2, "r", encoding="utf-8") as f2:
        r1 = list(csv.reader(f1))
        r2 = list(csv.reader(f2))
        
        if len(r1) != len(r2):
            print(f"FAILED: Different length. {file1}: {len(r1)}, {file2}: {len(r2)}")
            return False
            
        for i, (row1, row2) in enumerate(zip(r1, r2)):
            if row1 != row2:
                print(f"FAILED: Difference at line {i+1}")
                print(f"  {file1}: {row1}")
                print(f"  {file2}: {row2}")
                return False
    return True

if __name__ == "__main__":
    s1 = "baseline_snapshot_states.csv"
    s2 = "current_snapshot_states.csv"
    i1 = "baseline_snapshot_interactions.csv"
    i2 = "current_snapshot_interactions.csv"
    
    res_s = compare_csv(s1, s2)
    res_i = compare_csv(i1, i2)
    
    if res_s and res_i:
        print("SUCCESS: Snapshots are identical.")
        sys.exit(0)
    else:
        print("CRITICAL: Snapshots differ!")
        sys.exit(1)
