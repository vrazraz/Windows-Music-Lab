# Windows port (2026-10-12): deterministic stdlib UI builder based on build.sh.
import json, pathlib, re, sys

root = pathlib.Path(__file__).resolve().parents[1]
src = root / "build/tools/console"
examples = root / "build/tools/webui/example"
page = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else root / "windows/cache/full-ui/index.html"
page.parent.mkdir(parents=True, exist_ok=True)
folder = root.name
html = (src / "index.html").read_text(encoding="utf-8").replace('<script src="heresy-logo-words.js"></script>', "")
css = (src / "app.css").read_text(encoding="utf-8")


# HERESY 1169 (Viktor 07.10.2026: «три кнопочки svg -, +, reset для скейла… В минус шагом 2pt до минус 4, а в плюс… до макс 8pt…
# глобальный скейл шрифтов с минус 2 и плюс до 4»): every font size of the stylesheets, in px or pt (never 0), is written
# calc(N + var(--fs, 0pt)), so the text grows and the layout does not; the page sets --fs (☰, a lifted frame), unset it is 0
def scaled(text):
    text = re.sub(r"(font-size:\s*)(?!0(?:\.0+)?(?:px|pt)\b)(\d+(?:\.\d+)?(?:px|pt))(?=\s*[;}!])", r"\1calc(\2 + var(--fs, 0pt))", text)
    return re.sub(r"(\bfont:\s*(?:(?:italic|oblique|normal|bold|bolder|lighter|small-caps|[1-9]00)\s+)*)(\d+(?:\.\d+)?(?:px|pt))(?=[\s/])",
                  r"\1calc(\2 + var(--fs, 0pt))", text)


css = scaled(css)
css += "\n.or-only { display:none !important; }\n"
js = (src / "app.js").read_text(encoding="utf-8")
# The Windows page exposes only local Writer providers, and never reads or saves API keys.
writer_swaps = [
    ('$("chatUrl").value = recall("yue2.chatUrl") || "";', '$("chatUrl").value = recall("yue2.chatUrl") || window.WINDOWS_FULL_PORT.writerUrl || "";'),
    ('try { orKey = recall("yue2.orKey") || ""; } catch (error) { orKey = ""; }', 'orKey = "";'),
    ('$("assistProvider").value = saved.provider ? (saved.provider === "openrouter" ? "openrouter" : "engine") : (recall("yue2.chatUrl") ? "engine" : "openrouter");', '$("assistProvider").value = "engine";'),
    ('if ($("orRemember").checked) store("yue2.orKey", this.value.trim() || null);', 'return;'),
    ('store("yue2.orKey", this.checked ? ($("orKey").value.trim() || null) : null);', 'return;'),
    ('Writer: no chat server set. Engine → Chat server (vLLM, LM Studio, Ollama), or choose OpenRouter below.', 'Writer: no local chat server set. Configure an approved loopback chat endpoint under Engine. See windows/WRITER_AI_APPROVAL.md.'),
    ('does not answer. Start it there, or choose OpenRouter below. (Checked just now; entering the Writer checks again.)', 'does not answer. Start the approved local server. (Checked just now; entering the Writer checks again.)'),
]
for before, after in writer_swaps:
    if js.count(before) != 1:
        raise SystemExit("Writer source marker changed: " + before[:40])
    js = js.replace(before, after, 1)
ins = (src / "instrumental.js").read_text(encoding="utf-8")
helps = (src / "help.js").read_text(encoding="utf-8")
lorajs = (src / "loras.js").read_text(encoding="utf-8")
vaejs = (src / "vaes.js").read_text(encoding="utf-8")
themecss = (src / "themes.css").read_text(encoding="utf-8")
themecss = scaled(themecss)
themejs = (src / "themes.js").read_text(encoding="utf-8")

prompts = []
# HERESY 1035: our own examples (heresy/examples/*.json) come after the official ones, each with
# its "group" (Readings…); the page offers them by name and keeps "random" to the official set.
ours = root / "heresy" / "examples"   # build/tools/console -> Kit root
for path in (sorted(examples.glob("*.json")) if examples.is_dir() else []) + (sorted(ours.glob("*.json")) if ours.is_dir() else []):
    data = json.loads(path.read_text(encoding="utf-8"))
    prompts.append({k: data[k] for k in ("title", "style", "lyrics", "cot", "abc", "seed", "group")
                    if k in data and data[k] not in (None, "")})
# "</" inside a JSON string is written "<\/" so it can never close the script.
examples_js = ("window.YUE2_EXAMPLES = " +
               json.dumps(prompts, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ";")

for name, text, closer in (("app.css", css, "</style"), ("instrumental.js", ins, "</script"), ("help.js", helps, "</script"), ("loras.js", lorajs, "</script"), ("vaes.js", vaejs, "</script"), ("themes.css", themecss, "</style"), ("themes.js", themejs, "</script"), ("app.js", js, "</script")):
    if closer in text.lower():
        sys.exit(f"{name} contains '{closer}>', which would end its inlined block")

# Each marker must appear exactly once; the page is assembled from slices of the
# original, so inlined text can never be mistaken for a later marker.
swaps = [
    ('<link rel="stylesheet" href="app.css" />', "<style>\n" + css + "</style>"),
    ('<link rel="stylesheet" href="themes.css" />', "<style>\n" + themecss + "</style>"),
    ('<script src="examples.js"></script>', "<script>" + examples_js + "</script>"),
    ('<script src="instrumental.js"></script>', "<script>\n" + ins + "</script>"),
    ('<script src="help.js"></script>', "<script>\n" + helps + "</script>"),
    ('<script src="loras.js"></script>', "<script>\n" + lorajs + "</script>"),
    ('<script src="vaes.js"></script>', "<script>\n" + vaejs + "</script>"),
    ('<script src="themes.js"></script>', "<script>\n" + themejs + "</script>"),
    ('<script src="app.js"></script>', "<script>\n" + js + "</script>"),
]
# HERESY: our own modules (heresy-*.js) are inlined wherever index.html names them,
# so a new one needs no edit here. The same checks as the kit's files apply.
for name in re.findall(r'<script src="(heresy-[a-z0-9-]+\.js)"></script>', html):
    text = (src / name).read_text(encoding="utf-8")
    if "</script" in text.lower():
        sys.exit(f"{name} contains '</script>', which would end its inlined block")
    swaps.append((f'<script src="{name}"></script>', "<script>\n" + text + "</script>"))
# HERESY 1274 (Viktor 09.10.2026: «abcjs и шрифты ложи всё в репо… Минимум интернета из Студии на локальной машине»): what the page
# carries of others' (vendor/: abcjs, the fonts' faces) is inlined as our own is; the font files themselves the lab serves (/lab/fonts/)
for name in re.findall(r'<script src="(vendor/[A-Za-z0-9._-]+\.js)"></script>', html):
    text = (src / name).read_text(encoding="utf-8")
    if "</script" in text.lower():
        sys.exit(f"{name} contains '</script>', which would end its inlined block")
    swaps.append((f'<script src="{name}"></script>', "<script>\n" + text + "\n</script>"))
for name in re.findall(r'<link rel="stylesheet" href="(vendor/[A-Za-z0-9._-]+\.css)" />', html):
    text = (src / name).read_text(encoding="utf-8")
    if "</style" in text.lower():
        sys.exit(f"{name} contains '</style>', which would end its inlined block")
    swaps.append((f'<link rel="stylesheet" href="{name}" />', "<style>\n" + text + "</style>"))
found = []
for marker, replacement in swaps:
    count = html.count(marker)
    if count != 1:
        sys.exit(f"marker {marker!r} appears {count} times in index.html (want exactly 1)")
    found.append((html.index(marker), marker, replacement))
found.sort()
out, at = [], 0
for index, marker, replacement in found:
    out.append(html[at:index])
    out.append(replacement)
    at = index + len(marker)
out.append(html[at:])
result = "".join(out)

# The folder name is data: the page must not carry it, nor an absolute home path. External links whose
# name happens to match (upstream's own repo, which the CPP badge opens, and the collection's own repo, which
# the status note opens) are not paths, so they are left out.
EXTERNAL = ("https://github.com/ServeurpersoCom/yue2.cpp", "https://github.com/IronWolve/yue2-kit")
checked = re.sub(r"<!-- credits:.*?<!-- /credits -->", "", result, flags=re.S)   # the About card's upstream names
for url in EXTERNAL:   # the whole link (its text names the project too), then any bare mention of the URL
    checked = re.sub(r'<a\b[^>]*href="' + re.escape(url) + r'"[^>]*>.*?</a>', "", checked, flags=re.S)
    checked = checked.replace(url, "")
for bad in (folder, "/home/"):
    if bad and bad in checked:
        sys.exit(f"the page contains {bad!r}; paths and the folder name must not be baked in")

# Local mode also covers direct frontend chat requests, XHR, fonts and image URLs.
csp = "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://127.0.0.1:* http://localhost:* http://[::1]:*; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' data: blob:; object-src 'none'; base-uri 'self'"
guard = (root / "windows/full-local-mode.js").read_text(encoding="utf-8")
writer_ready_path = root / 'windows/state/writer/ready.json'
writer_config = {'localOnly': True}
if writer_ready_path.is_file():
    try:
        ready = json.loads(writer_ready_path.read_text(encoding='utf-8-sig'))
        if not isinstance(ready, dict):
            ready = {}
    except (OSError, ValueError):
        ready = {}
    if (ready.get('schema_version') == 1 and ready.get('verified') is True
            and ready.get('source_revision') == '8345f333951c661d166b00e6f9362e553768f292'
            and ready.get('endpoint') == 'http://127.0.0.1:41872/v1'
            and ready.get('alias') == 'Windows-Music-Lab-Writer'):
        writer_config.update(writerUrl='http://127.0.0.1:41872', writerAlias=ready['alias'])
if guard.count('window.WINDOWS_FULL_PORT = {localOnly: true};') != 1:
    raise SystemExit('Local mode configuration marker changed')
guard = guard.replace('window.WINDOWS_FULL_PORT = {localOnly: true};',
                      'window.WINDOWS_FULL_PORT = ' + json.dumps(writer_config) + ';', 1)
if "</script" in guard.lower():
    raise SystemExit("Unsafe closing script token in local-mode guard")
result = result.replace('<meta charset="utf-8" />', '<meta charset="utf-8" /><meta http-equiv="Content-Security-Policy" content="' + csp + '"><script>' + guard + '</script>', 1)
result = result.replace('<title>Ruach Studio</title>', '<title>Windows Music Lab — Full Studio</title>')
result = re.sub(r'<link rel="icon"[^>]*>', '<link rel="icon" id="favicon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2212%22 fill=%22%2324352d%22/%3E%3Ctext x=%2232%22 y=%2244%22 text-anchor=%22middle%22 font-family=%22sans-serif%22 font-size=%2242%22 fill=%22%23fffef9%22%3EW%3C/text%3E%3C/svg%3E">', result, count=1)
# A depth-aware span scan preserves nested source markup outside the old logo.
start = result.find('<span class="brand-logo"')
if start < 0:
    raise SystemExit("Expected upstream brand holder was not found")
depth = 0
end = None
for match in re.finditer(r'<(/?)span\b[^>]*>', result[start:]):
    depth += -1 if match.group(1) else 1
    if depth == 0:
        end = start + match.end()
        break
if end is None:
    raise SystemExit("Unbalanced upstream brand holder")
wordmark = '<span class="brand-logo" aria-label="Windows Music Lab"><span style="font:700 15px/1.05 sans-serif;letter-spacing:1px;display:inline-block">WINDOWS<br>MUSIC LAB</span></span>'
result = result[:start] + wordmark + result[end:]
result = result.replace('<div class="boot-logo" id="bootLogo"></div>', '<div class="boot-logo" id="bootLogo">Windows Music Lab</div>')
result = result.replace('Loading the Sound Heresy', 'Loading Windows Music Lab')
result = result.replace('<!-- /credits -->', '<p>Windows Music Lab: native Windows port of Ruach Studio by Viktor Zhuromskyy. <a href="https://github.com/vrazraz/Windows-Music-Lab">Source and licenses</a>. Local mode: cloud connections are blocked.</p><!-- /credits -->')
temporary = page.with_suffix(".part")
temporary.write_text(result, encoding="utf-8")
temporary.replace(page)
# the stats groups: every stylesheet and every script that was inlined
styles = (css, themecss)
scripts = (js, ins, helps, lorajs, vaejs, themejs)
sizes = [len(t.encode("utf-8")) for t in (html, "".join(styles), "".join(scripts), examples_js, result)]
lines = [t.count("\n") for t in (html, "".join(styles), "".join(scripts))]
print("\t".join(str(v) for v in sizes + lines + [len(prompts), len(styles), len(scripts)]))
