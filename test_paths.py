from core.file_paths import matches_exclusion
print("1.", matches_exclusion(".github/workflows", ".github/**"))
print("2.", matches_exclusion("./.github/workflows", ".github/**"))
print("3.", matches_exclusion("app/output", "app/output"))
print("4.", matches_exclusion("app/output/foo.py", "app/output"))
