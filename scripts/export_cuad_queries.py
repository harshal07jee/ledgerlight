import json
import os
from huggingface_hub import hf_hub_download

path = hf_hub_download(repo_id="theatticusproject/cuad", filename="CUAD_v1/CUAD_v1.json", repo_type="dataset")
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

c0 = data["data"][0]
cuad_queries = {}
for qa in c0["paragraphs"][0]["qas"]:
    q = qa["question"]
    s = q.find('"')
    e = q.find('"', s + 1)
    if s != -1 and e != -1:
        cat = q[s+1:e]
        cuad_queries[cat] = q

os.makedirs("data", exist_ok=True)
with open("data/cuad_official_queries.json", "w", encoding="utf-8") as f:
    json.dump(cuad_queries, f, indent=2)

print(f"Successfully saved {len(cuad_queries)} official queries to data/cuad_official_queries.json")
