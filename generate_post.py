# generate_post.py
import os
import requests
from base64 import b64encode
from dotenv import load_dotenv
import time

load_dotenv()

# ----- 必須設定（GitHub Secrets に設定） -----
WP_URL = os.getenv("WP_URL")  # 例: https://your-site.com
WP_USER = os.getenv("WP_USER")
WP_APP_PASS = os.getenv("WP_APP_PASS")
AFF_LINK = os.getenv("AFF_LINK", "https://affiliate.example/?ref=you")

# 任意（高品質時）
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")

# ----- 生成用の簡易キーワード（変更可） -----
PRIMARY_KEYWORD = os.getenv("PRIMARY_KEYWORD", "best marketing automation tools 2025")

# ---------------- ヘルパー ----------------
def call_openai(prompt):
    # If OPENAI_KEY present, use it (better quality)
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "gpt-4o-mini" if OPENAI_KEY else "gpt-3.5-turbo",
        "messages": [{"role": "system", "content": "You are an expert B2B SaaS writer."},
                     {"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 1600
    }
    r = requests.post(url, json=body, headers=headers, timeout=120)
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"]

def call_hf(prompt):
    # Use Hugging Face text-generation inference (free tier); choose a lightweight model
    # Note: token usage depends on model; if HF_TOKEN not set, fallback to a simple template
    if not HF_TOKEN:
        return fallback_generate(prompt)
    url = "https://api.openai-hf.example"  # placeholder — use your model endpoint if known
    # Many HF endpoints vary; below is a generic pattern for HF Inference API:
    hf_url = "https://api-inference.huggingface.co/models/gpt2"  # fallback small model (not great)
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    r = requests.post(hf_url, headers=headers, json={"inputs": prompt, "parameters": {"max_new_tokens": 800}})
    r.raise_for_status()
    out = r.json()
    if isinstance(out, list) and "generated_text" in out[0]:
        return out[0]["generated_text"]
    # many models return plain text:
    return out.get("generated_text") or str(out)

def fallback_generate(prompt):
    # Very basic deterministic template if no external model available
    title = f"{PRIMARY_KEYWORD} — A practical guide"
    body = f"<h2>Introduction</h2><p>This article provides a concise overview for '{PRIMARY_KEYWORD}'.</p>"
    body += "<h2>Top picks</h2><ul><li>Tool A — Good for small teams</li><li>Tool B — Good for enterprise</li></ul>"
    body += f"<p>For more details and an affiliate offer, visit {AFF_LINK}</p>"
    return f"{title}\n\n{body}\n\n<!-- AUTO_GENERATED -->"

def generate_content():
    prompt = (
        f"Write an SEO-friendly article (~900-1400 words) about: '{PRIMARY_KEYWORD}'. "
        "Include: title, short meta description (<=150 chars), H1, H2 sections, 3 FAQs, and a final CTA paragraph with this affiliate link: "
        f"{AFF_LINK}. Return plain text starting with the title on the first line."
    )
    try:
        if OPENAI_KEY:
            return call_openai(prompt)
        else:
            return call_hf(prompt)
    except Exception as e:
        print("Model call failed:", e)
        print("Using fallback generator.")
        return fallback_generate(prompt)

# ---------------- WordPress 投稿 ----------------
def post_to_wp(title, html_content, excerpt=""):
    auth = b64encode(f"{WP_USER}:{WP_APP_PASS}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json"
    }
    payload = {
        "title": title,
        "content": html_content,
        "excerpt": excerpt,
        "status": "draft"  # draft にして手動チェックを推奨
    }
    r = requests.post(f"{WP_URL}/wp-json/wp/v2/posts", headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

# ---------------- Unsplash 画像取得（無料・API不要） ----------------
def fetch_unsplash_image(query="saas dashboard"):
    # Unsplash Source can give a random image for a query without API key:
    url = f"https://source.unsplash.com/1200x630/?{requests.utils.quote(query)}"
    # This returns a redirect to an image; we can download it
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content  # binary jpeg

def upload_media_to_wp(binary_image, filename="hero.jpg"):
    auth = b64encode(f"{WP_USER}:{WP_APP_PASS}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "image/jpeg"
    }
    r = requests.post(f"{WP_URL}/wp-json/wp/v2/media", headers=headers, data=binary_image, timeout=60)
    r.raise_for_status()
    return r.json()

# ---------------- main ----------------
def main():
    print("Generating content...")
    txt = generate_content()
    # Simple parse: first non-empty line as title, rest as html-like content
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    title = lines[0] if lines else PRIMARY_KEYWORD
    body = "\n".join(lines[1:]) if len(lines) > 1 else ""
    # If body is plain text, wrap paragraphs
    if "<p>" not in body and "<h" not in body:
        paragraphs = [f"<p>{p}</p>" for p in body.split("\n\n") if p.strip()]
        body = "\n".join(paragraphs)
    excerpt = body[:140]
    # mark auto-generated
    if "<!-- AUTO_GENERATED -->" not in body:
        body += "\n\n<!-- AUTO_GENERATED -->"
    # Post to WP
    try:
        res = post_to_wp(title, body, excerpt)
        post_id = res.get("id")
        print("Draft created. Post ID:", post_id)
        # Fetch an Unsplash image and attach
        try:
            img = fetch_unsplash_image("saas dashboard")
            media = upload_media_to_wp(img, filename="hero.jpg")
            media_id = media.get("id")
            if post_id and media_id:
                # Attach as featured_media
                auth = b64encode(f"{WP_USER}:{WP_APP_PASS}".encode()).decode()
                headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
                upd = requests.post(f"{WP_URL}/wp-json/wp/v2/posts/{post_id}", headers=headers, json={"featured_media": media_id}, timeout=30)
                upd.raise_for_status()
                print("Featured image set.")
        except Exception as e:
            print("Image attach failed:", e)
    except Exception as e:
        print("Failed to post:", e)

if __name__ == "__main__":
    main()
