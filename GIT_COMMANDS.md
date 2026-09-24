# 🔄 Git Commands - Main Branch

## 📍 Current Status
```
Branch: main
Status: Up to date with 'origin/main'
```

---

## ⚡ Quick Commands

### FETCH from main (Download only - SAFE)
```bash
git fetch origin main
```
✓ Downloads latest changes from remote
✓ Does NOT modify your local code
✓ Safe to use anytime

### PULL from main (Download + Merge)
```bash
git pull origin main
```
✓ Downloads latest changes
✓ Merges into your local code
✓ Updates your working directory

---

## 🎯 Most Useful Commands

### Check current branch
```bash
git branch
```

### Check status
```bash
git status
```

### View latest commits
```bash
git log --oneline -10
```

### View all remote branches
```bash
git branch -r
```

### See what changed (before pulling)
```bash
git fetch origin main
git diff main origin/main
```

---

## 📋 Step-by-Step Guide

### If you want JUST the latest code (safe):
```bash
# Step 1: Fetch (download)
git fetch origin main

# Step 2: Check what changed
git diff main origin/main

# Step 3: Merge if happy
git merge origin/main
```

### If you want to update quickly:
```bash
git pull origin main
```

### If you're on a different branch:
```bash
# Switch to main
git checkout main

# Pull latest
git pull origin main
```

---

## ⚠️ Important Notes

- **FETCH** is always safe - it just downloads, never modifies your code
- **PULL** = FETCH + MERGE - this changes your code
- You are **already on main** branch
- Your branch is **already up to date**

---

## 🚀 Copy-Paste These

**Safe fetch:**
```bash
git fetch origin main
```

**Update with latest:**
```bash
git pull origin main
```

**Check status:**
```bash
git status
```

**See commits:**
```bash
git log --oneline
```

---

## 📖 For More Help

- `git help fetch` - Full documentation on fetch
- `git help pull` - Full documentation on pull
- `git help branch` - Full documentation on branches
