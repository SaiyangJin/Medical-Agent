import difflib

candidates = ["高皿压",""]
result = difflib.get_close_matches("高血压", candidates, n=5, cutoff=0.9)
print(result)  # → ['高血压']