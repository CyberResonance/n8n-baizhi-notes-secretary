"""
test_secretary.py - Verification suite for Baizhi Notes Secretary
Tests:
1. Note Prefix Matching (!N, !notes, !note, !todo)
2. Normalization & Sanitization
3. Deduplication Algorithm (Exact matches + Fuzzy token overlap)
4. Classification (Tasks, Ideas, General Notes)
5. Obsidian Markdown & Discord Embed Generation
"""

import re
import unittest
from datetime import datetime, timezone

def normalize_text(text: str) -> str:
    """Normalizes text for deduplication comparison."""
    if not text:
        return ""
    # Lowercase, remove markdown/punctuation, strip excessive whitespace
    text = text.lower()
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'[^\w\s]', '', text, flags=re.UNICODE)
    return ' '.join(text.split()).strip()

def strip_prefix(content: str) -> tuple[bool, str]:
    """
    Checks if message starts with supported note prefix (!N, !notes, !note, !todo, !task).
    Returns (is_valid, stripped_content).
    """
    if not content:
        return False, ""
    pattern = r'^\s*!(n|notes|note|todo|task)\b[:\s]*'
    match = re.match(pattern, content, re.IGNORECASE)
    if match:
        clean = content[match.end():].strip()
        return True, clean
    return False, content.strip()

def is_near_duplicate(norm1: str, norm2: str, similarity_threshold: float = 0.70) -> bool:
    """Checks if two normalized texts are duplicates or slight variations."""
    if norm1 == norm2:
        return True
    # Containment check (e.g. one string completely contains the other)
    if norm1 in norm2 or norm2 in norm1:
        shorter_len = min(len(norm1), len(norm2))
        longer_len = max(len(norm1), len(norm2))
        if shorter_len / longer_len >= 0.60:
            return True
    # Jaccard word similarity
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    if not words1 or not words2:
        return False
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    jaccard = intersection / union if union > 0 else 0.0
    if jaccard >= similarity_threshold:
        return True
    # Word subset check (all words of shorter text appear in longer text)
    shorter_words = words1 if len(words1) <= len(words2) else words2
    longer_words = words2 if len(words1) <= len(words2) else words1
    if shorter_words.issubset(longer_words) and len(shorter_words) >= 3:
        return True
    return False

def classify_note(text: str) -> str:
    """Classifies note into TODO, Idea, or Note."""
    lower = text.lower()
    todo_keywords = ['todo', 'task', 'zadanie', 'do zrobienia', 'kupić', 'buy', 'fix', 'napraw', 'call', 'zadzwoń', 'deadline', 'wysłać', 'send']
    idea_keywords = ['idea', 'pomysł', 'concept', 'koncepcja', 'brainstorm', 'feature', 'think about', 'rozważyć']
    
    if any(kw in lower for kw in todo_keywords) or lower.startswith('- [ ]'):
        return 'TODO'
    elif any(kw in lower for kw in idea_keywords):
        return 'Idea'
    return 'Note'

def process_and_deduplicate_notes(raw_messages: list[dict], similarity_threshold: float = 0.80, max_age_hours: float = 24.0, reference_time: datetime = None) -> dict:
    """
    Filters messages with note prefix, discards entries older than max_age_hours (default 24h),
    deduplicates exact and near-repeats, and categorizes the final items.
    """
    accepted_notes = []
    duplicate_count = 0
    expired_count = 0
    now = reference_time or datetime.now(timezone.utc)
    
    for msg in raw_messages:
        raw_text = msg.get("content", "")
        author = msg.get("author", "User")
        ts_raw = msg.get("timestamp", now.isoformat())
        
        # 1. 24-Hour Cutoff Check
        try:
            if isinstance(ts_raw, str):
                msg_time = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            elif isinstance(ts_raw, (int, float)):
                msg_time = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            else:
                msg_time = now
            if msg_time.tzinfo is None:
                msg_time = msg_time.replace(tzinfo=timezone.utc)
        except Exception:
            msg_time = now
            
        if (now - msg_time).total_seconds() > max_age_hours * 3600:
            expired_count += 1
            continue
        
        is_valid, cleaned_text = strip_prefix(raw_text)
        if not is_valid or not cleaned_text:
            continue
            
        norm = normalize_text(cleaned_text)
        
        # Check against already accepted notes for deduplication
        is_duplicate = False
        for existing in accepted_notes:
            existing_norm = existing["normalized"]
            if is_near_duplicate(norm, existing_norm, similarity_threshold):
                # Retain longer/more detailed version if current is richer
                if len(cleaned_text) > len(existing["clean_text"]):
                    existing["clean_text"] = cleaned_text
                    existing["normalized"] = norm
                    existing["category"] = classify_note(cleaned_text)
                is_duplicate = True
                break
                
        if is_duplicate:
            duplicate_count += 1
            continue
            
        category = classify_note(cleaned_text)
        accepted_notes.append({
            "id": msg.get("id", str(len(accepted_notes))),
            "author": author,
            "raw": raw_text,
            "clean_text": cleaned_text,
            "normalized": norm,
            "category": category,
            "timestamp": ts_raw
        })
        
    return {
        "notes": accepted_notes,
        "total_received": len(raw_messages),
        "total_accepted": len(accepted_notes),
        "duplicate_count": duplicate_count,
        "expired_count": expired_count
    }

def generate_obsidian_markdown(date_str: str, processed: dict) -> str:
    """Generates Obsidian-ready markdown note."""
    notes = processed["notes"]
    todos = [n for n in notes if n["category"] == "TODO"]
    ideas = [n for n in notes if n["category"] == "Idea"]
    general = [n for n in notes if n["category"] == "Note"]
    
    md = [
        "---",
        f"title: Daily Notes & TODO - {date_str}",
        f"date: {date_str}",
        "author: Baizhi Virtual Assistant",
        "tags:",
        "  - baizhi/daily-digest",
        "  - n8n/secretary",
        "  - todo",
        "  - productivity",
        f"total_notes: {processed['total_accepted']}",
        f"duplicates_filtered: {processed['duplicate_count']}",
        "---",
        "",
        f"# 🌸 Baizhi Daily Executive Digest - {date_str}",
        "",
        "> [!NOTE] Baizhi's Daily Summary",
        f"> Hey Kacper! Today I processed **{processed['total_accepted']} unique items** from your Discord stream (filtered out {processed['duplicate_count']} duplicate entries). Here is your organized digest and action plan for today!",
        "",
        "## 📋 Actionable Tasks & TODOs"
    ]
    
    if todos:
        for t in todos:
            md.append(f"- [ ] {t['clean_text']}")
    else:
        md.append("- [x] *No urgent pending tasks logged today.*")
        
    md.extend([
        "",
        "## 💡 Captured Ideas & Insights"
    ])
    
    if ideas:
        for i in ideas:
            md.append(f"- 💡 **{i['clean_text']}**")
    else:
        md.append("- *No new ideas recorded today.*")
        
    md.extend([
        "",
        "## 📝 General Notes & Thoughts"
    ])
    
    if general:
        for g in general:
            md.append(f"- {g['clean_text']}")
    else:
        md.append("- *No general notes recorded today.*")
        
    md.extend([
        "",
        "## 🗂️ Audit Log of Raw Entries",
        "| Time | Category | Text |",
        "|---|---|---|"
    ])
    for n in notes:
        time_display = n["timestamp"].split("T")[1][:5] if "T" in n["timestamp"] else n["timestamp"]
        safe_text = n["clean_text"].replace("|", "\\|")
        md.append(f"| `{time_display}` | `{n['category']}` | {safe_text} |")
        
    md.append("")
    return "\n".join(md)

def generate_discord_embed(date_str: str, processed: dict) -> dict:
    """Generates Discord Rich Embed payload."""
    notes = processed["notes"]
    todos = [n for n in notes if n["category"] == "TODO"]
    ideas = [n for n in notes if n["category"] == "Idea"]
    general = [n for n in notes if n["category"] == "Note"]
    
    fields = []
    
    # Field 1: Tasks
    todo_lines = [f"• [ ] {t['clean_text']}" for t in todos[:8]]
    fields.append({
        "name": "📋 Actionable TODOs & Tasks",
        "value": "\n".join(todo_lines) if todo_lines else "*No pending tasks for today!*",
        "inline": False
    })
    
    # Field 2: Ideas
    idea_lines = [f"• 💡 {i['clean_text']}" for i in ideas[:6]]
    if idea_lines:
        fields.append({
            "name": "💡 Ideas & Brainstorms",
            "value": "\n".join(idea_lines),
            "inline": False
        })
        
    # Field 3: General Notes
    note_lines = [f"• {g['clean_text']}" for g in general[:6]]
    if note_lines:
        fields.append({
            "name": "📝 Notes & Highlights",
            "value": "\n".join(note_lines),
            "inline": False
        })
        
    embed = {
        "title": f"🌸 Baizhi Daily Executive Digest — {date_str}",
        "description": f"Hey Kacper! I've synthesized your stream of consciousness from today.\n**{processed['total_accepted']} unique notes** retained, **{processed['duplicate_count']} duplicates** filtered out.",
        "color": 10181046,  # #9B59B6 Purple
        "fields": fields,
        "footer": {
            "text": "Baizhi Virtual Assistant • n8n Executive Secretary"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return {"embeds": [embed]}

class TestNotesSecretary(unittest.TestCase):
    def test_prefix_detection(self):
        self.assertEqual(strip_prefix("!N kupić mleko")[0], True)
        self.assertEqual(strip_prefix("!n kupić mleko")[1], "kupić mleko")
        self.assertEqual(strip_prefix("!notes Review PR #44")[0], True)
        self.assertEqual(strip_prefix("!notes Review PR #44")[1], "Review PR #44")
        self.assertEqual(strip_prefix("!note Remember to call John")[0], True)
        self.assertEqual(strip_prefix("!todo Finish homework")[0], True)
        self.assertEqual(strip_prefix("Just a normal conversation")[0], False)
        self.assertEqual(strip_prefix("not a prefix!n")[0], False)

    def test_deduplication(self):
        messages = [
            {"content": "!N Review security architecture on AWS", "id": "1"},
            {"content": "!N Review security architecture on AWS", "id": "2"},  # Exact duplicate
            {"content": "!notes review security architecture on AWS!", "id": "3"}, # Normalized duplicate
            {"content": "!N Review security architecture on AWS and update Terraform", "id": "4"}, # Near match (enriched)
            {"content": "!N Kupić chleb i masło", "id": "5"},
            {"content": "!n kupić chleb i masło", "id": "6"}, # Duplicate
            {"content": "!notes Pomysł na nowy projekt AI", "id": "7"},
            {"content": "Random chatter without prefix", "id": "8"}, # Ignored
        ]
        res = process_and_deduplicate_notes(messages)
        self.assertEqual(res["total_received"], 8)
        self.assertEqual(res["duplicate_count"], 4)
        self.assertEqual(res["total_accepted"], 3)
        
        # Verify enriched note survived
        clean_texts = [n["clean_text"] for n in res["notes"]]
        self.assertIn("Review security architecture on AWS and update Terraform", clean_texts)
        self.assertIn("Kupić chleb i masło", clean_texts)
        self.assertIn("Pomysł na nowy projekt AI", clean_texts)

    def test_polish_diacritics_and_multiline(self):
        messages = [
            {"content": "!N Zrobić kopię zapasową bazy danych:\n1. Postgres\n2. Redis", "id": "p1"},
            {"content": "!n zrobić kopię zapasową bazy danych: 1. postgres 2. redis", "id": "p2"}, # Dupe
        ]
        res = process_and_deduplicate_notes(messages)
        self.assertEqual(res["total_accepted"], 1)
        self.assertEqual(res["duplicate_count"], 1)

    def test_markdown_generation(self):
        messages = [
            {"content": "!N Fix the deployment bug in n8n container", "id": "1", "timestamp": "2026-09-30T10:15:00Z"},
            {"content": "!notes Idea: build automated secretary for Obsidian", "id": "2", "timestamp": "2026-09-30T14:30:00Z"},
            {"content": "!N Note about tomorrow's schedule", "id": "3", "timestamp": "2026-09-30T16:00:00Z"},
        ]
        # Fixed reference time: the 24 h window filter would otherwise drop these fixed-date notes on any later day.
        res = process_and_deduplicate_notes(messages, reference_time=datetime(2026, 9, 30, 21, 0, 0, tzinfo=timezone.utc))
        md = generate_obsidian_markdown("2026-09-30", res)
        self.assertIn("# 🌸 Baizhi Daily Executive Digest - 2026-09-30", md)
        self.assertIn("- [ ] Fix the deployment bug in n8n container", md)
        self.assertIn("Idea: build automated secretary for Obsidian", md)
        self.assertIn("baizhi/daily-digest", md)

    def test_24h_window_filter(self):
        ref_now = datetime(2026, 9, 30, 21, 0, 0, tzinfo=timezone.utc)
        messages = [
            # Note from 2 hours ago (today) -> Should pass
            {"content": "!N Today's urgent note", "id": "1", "timestamp": "2026-09-30T19:00:00Z"},
            # Note from 22 hours ago (within 24h window) -> Should pass
            {"content": "!notes Today's morning thought", "id": "2", "timestamp": "2026-09-29T23:30:00Z"},
            # Note from 2 days ago (yesterday / older than 24h) -> Should be DISCARDED
            {"content": "!N Yesterday's already completed task", "id": "3", "timestamp": "2026-09-28T14:00:00Z"},
            # Note from last week -> Should be DISCARDED
            {"content": "!todo Ancient task from last week", "id": "4", "timestamp": "2026-09-20T10:00:00Z"},
        ]
        res = process_and_deduplicate_notes(messages, reference_time=ref_now)
        self.assertEqual(res["total_accepted"], 2)
        self.assertEqual(res["expired_count"], 2)
        clean_texts = [n["clean_text"] for n in res["notes"]]
        self.assertIn("Today's urgent note", clean_texts)
        self.assertIn("Today's morning thought", clean_texts)
        self.assertNotIn("Yesterday's already completed task", clean_texts)
        self.assertNotIn("Ancient task from last week", clean_texts)

if __name__ == "__main__":
    unittest.main()
