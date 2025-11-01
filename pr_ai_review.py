import os
import requests
from dotenv import load_dotenv
from openai import OpenAI
import json

# Load environment variables
load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO = os.getenv("GITHUB_REPOSITORY")
PR_NUMBER = os.getenv("PR_NUMBER")

if not all([GITHUB_TOKEN, OPENAI_API_KEY, REPO, PR_NUMBER]):
    raise ValueError("Missing environment variables. Please check your .env file.")

client = OpenAI(api_key=OPENAI_API_KEY)
headers = {"Authorization": f"token {GITHUB_TOKEN}"}

# Step 1: Fetch PR files
files_url = f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}/files"
response = requests.get(files_url, headers=headers)
if response.status_code != 200:
    raise Exception(f"Failed to fetch PR files: {response.text}")

files = response.json()
print(f"[AI-PR-Review] Fetched {len(files)} files from PR #{PR_NUMBER}")

# Step 2: Build diff text for AI
diff_summary = ""
for f in files:
    if "patch" in f:
        diff_summary += f"File: {f['filename']}\n{f['patch']}\n\n"

# Step 3: Ask OpenAI for inline-style JSON review
prompt = f"""
You are a concise AI code reviewer.
Analyze the following GitHub pull request diff and suggest *only brief, line-specific corrections* (no summaries).

For each issue, output a JSON array of objects with:
- file: filename (exactly as shown)
- line: line number where issue occurs
- comment: a short, clear suggestion (<= 1 sentence)

If a line is correct, do not comment on it.

Respond in *pure JSON only*, with no markdown fences or explanations.

Here is the PR diff:
{diff_summary}
"""

print("[AI-PR-Review] Querying OpenAI for inline feedback...")
try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    ai_text = response.choices[0].message.content.strip()

    # Step 4: Parse JSON response
    if ai_text.startswith("```"):
        ai_text = ai_text.strip("```json").strip("```")
    comments = json.loads(ai_text)

    print(f"✅ AI Review Generated: {len(comments)} inline comments")

    # Step 5: Get latest commit SHA
    pr_url = f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}"
    pr_data = requests.get(pr_url, headers=headers).json()
    commit_id = pr_data["head"]["sha"]

    # Step 6: Post as inline PR review
    # Step 6: Post as inline PR review
    review_url = f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}/reviews"
    review_data = {
        "commit_id": commit_id,
        "body": "🤖 AI Inline Code Review",
        "event": "COMMENT",
        "comments": [
            {
                "path": c["file"],
                "line": c["line"],
                "side": "RIGHT",
                "body": c["comment"]
            }
            for c in comments
        ],
    }

    gh_response = requests.post(review_url, headers=headers, json=review_data)
    if gh_response.status_code in [200, 201]:
        print("✅ Inline comments posted successfully to PR.")
    else:
        print(f"❌ Failed to post inline review: {gh_response.status_code}\n{gh_response.text}")


except Exception as e:
    print(f"❌ OpenAI or GitHub error: {e}")
