import os
import re

# Comprehensive regex for emojis
def remove_emojis(text):
    # This regex covers most common emojis and symbols
    # It targets characters in the supplemental planes where most emojis live
    return re.sub(r'[^\x00-\x7F\u00C0-\u017F\u0180-\u024F\u1E00-\u1EFF\u2000-\u206F\u2070-\u209F\u20A0-\u20CF\u2100-\u214F\u2150-\u218F\u2190-\u21FF\u2200-\u22FF\u2300-\u23FF\u2400-\u243F\u2440-\u245F\u2460-\u24FF\u2500-\u257F\u2580-\u259F\u25A0-\u25FF\u2600-\u26FF\u2700-\u27BF\u2800-\u28FF\u2900-\u297F\u2980-\u29FF\u2A00-\u2AFF\u2B00-\u2BFF\u2C00-\u2C5F\u2C60-\u2C7F\u2C80-\u2CFF\u2D00-\u2D2F\u2D30-\u2D7F\u2D80-\u2DDF\u2E00-\u2E7F\u2E80-\u2EFF\u2F00-\u2FDF\u2FF0-\u2FFF\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u3100-\u312F\u3130-\u318F\u3190-\u319F\u31A0-\u31BF\u31C0-\u31EF\u31F0-\u31FF\u3200-\u32FF\u3300-\u33FF\u3400-\u4DBF\u4E00-\u9FFF\uA000-\uA48F\uA490-\uA4CF\uA4D0-\uA4FF\uA500-\uA63F\uA640-\uA69F\uA6A0-\uA6FF\uA700-\uA71F\uA720-\uA7FF\uA800-\uA82F\uA830-\uA83F\uA840-\uA87F\uA880-\uA8DF\uA8E0-\uA8FF\uA900-\uA92F\uA930-\uA95F\uA960-\uA97F\uA980-\uA9DF\uA9E0-\uA9FF\uAA00-\uAA5F\uAA60-\uAA7F\uAA80-\uAADF\uAAE0-\uAAFF\uAB00-\uAB2F\uAB30-\uAB6F\uAB70-\uABBF\uABC0-\uABFF\uAC00-\uD7AF\uD7B0-\uD7FF\uF900-\uFAFF\uFB00-\uFB4F\uFB50-\uFDFF\uFE00-\uFE0F\uFE10-\uFE1F\uFE20-\uFE2F\uFE30-\uFE4F\uFE50-\uFE6F\uFE70-\uFEFF\uFF00-\uFFEF\uFFF0-\uFFFF]+', 
                  lambda m: ''.join(c for c in m.group() if ord(c) < 0x10000), text)

# Actually, let's use a simpler and more reliable way to remove non-BMP characters (which include most emojis)
def strip_emojis(text):
    # This removes all characters outside the Basic Multilingual Plane (BMP)
    # Most emojis are in the Supplementary Multilingual Plane (SMP)
    # Also remove some specific common symbols in BMP like 🛠️, 🚀, etc.
    text = "".join(c for c in text if ord(c) < 0x10000)
    # Remove specific BMP symbols if needed
    symbols_to_remove = ["📜", "🐉", "🎡", "🛠", "🚀", "🌟", "🎯", "✅", "🔍", "💡", "📊", "🌀", "🏛", "🔬", "🛡", "🌿", "🤝"]
    for s in symbols_to_remove:
        text = text.replace(s, "")
    return text

for root, dirs, files in os.walk('.'):
    for file in files:
        if file.endswith('.md'):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                new_content = strip_emojis(content)
                if content != new_content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Cleaned {path}")
            except Exception as e:
                print(f"Error processing {path}: {e}")
