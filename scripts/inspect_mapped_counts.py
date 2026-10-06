import json
from huggingface_hub import hf_hub_download

path = hf_hub_download(repo_id="theatticusproject/cuad", filename="CUAD_v1/CUAD_v1.json", repo_type="dataset")
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

contracts = sorted(data["data"], key=lambda c: c["title"])
test_contracts = contracts[int(len(contracts) * 0.9):]
print("Test contracts:", len(test_contracts))

mapped_cats = ["Change Of Control", "Most Favored Nation", "Exclusivity", "Uncapped Liability"]
for cat in mapped_cats:
    pos = 0
    total_answers = 0
    for c in test_contracts:
        for qa in c["paragraphs"][0]["qas"]:
            if f'"{cat}"' in qa["question"]:
                ans = qa.get("answers", [])
                if len(ans) > 0:
                    pos += 1
                    total_answers += len(ans)
    print(f"{cat}: {pos}/51 contracts have clause (total {total_answers} gold spans)")
