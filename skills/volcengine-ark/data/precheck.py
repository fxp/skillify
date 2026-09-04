#!/usr/bin/env python3
"""Dump the fact-bearing tokens from every eval output so grading can cite exact lines."""
import re, sys, os, glob
PATTERNS = {
 "base_url": r"https?://ark\.cn-beijing\.volces\.com/api/[a-z0-9/._-]*|ark\.cn-beijing\.volcengineapi\.com[^\s\"']*|openspeech\.bytedance\.com[^\s\"']*",
 "model": r"\b(doubao-[a-z0-9.\-]+|glm-[a-z0-9.\-]+|kimi-[a-z0-9.\-]+|deepseek-[a-z0-9.\-]+|minimax-[a-z0-9.\-]+|ark-code-latest|claude-[a-z0-9.\-]+)\b",
 "role_developer": r"[\"']developer[\"']",
 "thinking": r"thinking[\"']?\s*[:=]\s*\{[^}]*\}|reasoning_effort[\"']?\s*[:=]\s*[\"'][a-z]+[\"']|CLAUDE_CODE_EXTRA_BODY[^\n]*",
 "max_tokens": r"max_tokens[\"']?\s*[:=]\s*\d+|max_completion_tokens[\"']?\s*[:=]\s*\d+|max_output_tokens[\"']?\s*[:=]\s*\d+",
 "size": r"[\"']size[\"']\s*[:=]\s*[\"'][^\"']+[\"']",
 "env_keys": r"[A-Z_]*(ARK|VOLC|PLAN|ANTHROPIC|AGENT)[A-Z_]*(KEY|TOKEN|SECRET)[A-Z_]*",
 "claude_env": r"ANTHROPIC_[A-Z_]+|CLAUDE_CODE_[A-Z_]+|hasCompletedOnboarding",
 "action": r"Action=?[\"']?\s*[:=]?\s*[\"']?([A-Z][A-Za-z]+)|[\"']Action[\"']\s*:\s*[\"']([A-Za-z]+)[\"']",
 "embed_path": r"embeddings(/multimodal)?|data\[0\]\[[\"']embedding[\"']\]|data\[[\"']embedding[\"']\]|\.data\[0\]\.embedding|\[\"data\"\]\[\"embedding\"\]|dimensions?[\"']?\s*[:=]\s*\d+",
 "compat": r"supportsDeveloperRole[^\n]*",
 "stream_usage": r"include_usage[^\n]*|\[DONE\]",
}
root = sys.argv[1] if len(sys.argv) > 1 else "iteration-1"
for d in sorted(glob.glob(f"{root}/eval-*/*/run-1/outputs")):
    print(f"\n######## {d}")
    files = [f for f in glob.glob(f"{d}/**/*", recursive=True) if os.path.isfile(f)]
    print("files:", [os.path.relpath(f, d) for f in files])
    text = ""
    for f in files:
        try: text += f"\n### {os.path.relpath(f,d)}\n" + open(f, errors="replace").read()
        except Exception as e: print("read fail", f, e)
    for k, p in PATTERNS.items():
        hits = sorted(set(m.group(0) for m in re.finditer(p, text)))
        if hits: print(f"  {k}: {hits[:25]}")
