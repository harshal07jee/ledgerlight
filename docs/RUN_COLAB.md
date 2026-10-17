# Running the CUAD Evaluation on Free Google Colab GPU

This guide provides step-by-step instructions for running the complete, un-truncated 51-contract, 41-category CUAD benchmark evaluation (`scripts/colab_cuad_eval.py`) on a free Google Colab GPU.

---

### Step 1: Open Google Colab and Select GPU Runtime

1. Go to [colab.research.google.com](https://colab.research.google.com) and create a **New Notebook**.
2. Navigate to **Runtime** > **Change runtime type** in the top menu.
3. Under **Hardware accelerator**, select **T4 GPU** (available on the free tier).
4. Click **Save**.

Verify GPU allocation by running this in the first cell:
```python
!nvidia-smi
```
*(You should see an NVIDIA T4 GPU with 15GB VRAM listed).*

---

### Step 2: Get Code and Data into Colab

Choose **Option A** (recommended if repo is on GitHub) or **Option B** (direct upload):

#### Option A: Clone via GitHub (Private or Public Repository)
If your repository is private, generate a GitHub Personal Access Token (classic with `repo` scope or fine-grained with read access to contents) from [github.com/settings/tokens](https://github.com/settings/tokens).

In a code cell:
```bash
# Clone the repository (replace <GITHUB_TOKEN>, <OWNER>, and <REPO>)
!git clone https://<GITHUB_TOKEN>@github.com/<OWNER>/<REPO>.git repo
%cd repo
```

#### Option B: Upload Local Project as ZIP
If you prefer not to use a GitHub token:
1. On your local machine, zip the repository folder (or download a zip archive).
2. In the left sidebar of Google Colab, click the **Folder icon** (Files).
3. Click the **Upload to session storage** button and upload your `.zip` file.
4. In a code cell, unzip the project and enter the directory:
```bash
!unzip -q ledgerlight.zip -d /content/ledgerlight
%cd /content/ledgerlight
```

---

### Step 3: Install Required Dependencies

Run the following cell to install the required libraries:
```bash
!pip install -q transformers datasets huggingface_hub scikit-learn torch numpy
```

---

### Step 4: Execute the Evaluation Script

Run the evaluation script with un-truncated sliding-window inference across all 51 test contracts and all 41 categories:

```bash
!python scripts/colab_cuad_eval.py
```

#### Expected Runtime & Output:
- **Expected Runtime**: **15 to 25 minutes** total on a free T4 GPU (~15–30 seconds per contract depending on text length).
- **Console Output**: Prints contract progress, chunk count, runtime per contract, and live logs.
- At completion, it prints:
  1. The Requirement 4 anti-synthetic verification audit results.
  2. The official per-category AUPR table for all 41 categories.
  3. The macro-mean AUPR and Precision @ 80% Recall.
  4. The Wilson confidence intervals and error rates at confidence thresholds 0.85 and 0.50 for diligence categories.

---

### Step 5: How to Resume if Colab Disconnects

Free Google Colab sessions can occasionally disconnect or restart. The evaluation script includes automatic checkpointing:
1. Progress is saved after **every single contract** into `scripts/colab_cuad_checkpoint.json`.
2. If your session disconnects:
   - Reconnect to a T4 GPU runtime.
   - Ensure the repository and `scripts/colab_cuad_checkpoint.json` are present in the working directory (if the VM was recycled, re-upload or clone and restore your checkpoint).
   - Re-run `!python scripts/colab_cuad_eval.py`.
   - The script will detect the existing checkpoint (`Resuming from checkpoint (X contracts already evaluated)`) and resume from contract `X+1` without repeating prior inference.

---

### Step 6: Download Evaluation Artifacts Back to Local Machine

Once the script completes, download the generated artifacts from Colab:

Run this code cell to trigger direct browser downloads:
```python
from google.colab import files

files.download('scripts/cuad_predictions.csv')
files.download('scripts/colab_cuad_checkpoint.json')
files.download('scripts/colab_cuad_run.log')
```

Or locate them in the Colab left sidebar file browser:
1. `scripts/cuad_predictions.csv` (contains the 2,091 real model prediction rows with scores, margins, spans, and IoUs).
2. `scripts/colab_cuad_checkpoint.json` (checkpoint cache).
3. `scripts/colab_cuad_run.log` (execution run log with exact package versions, GPU model, and git commit hash).

Copy `cuad_predictions.csv` into your local `docs/cuad_predictions.csv` repository path.
