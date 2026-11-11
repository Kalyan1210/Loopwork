#!/usr/bin/env python3
"""Build report/standalone.html: the whole report (data, all traces, swarm replay) in one file that opens without a server."""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core
R = os.path.join(core.ROOT, "report")
esc = lambda s: s.replace("</script", "<\\/script")
page = open(os.path.join(R, "index.html")).read()
data = esc(open(os.path.join(R, "data", "lab.js")).read()) + "\n" + "\n".join(esc(open(p).read()) for p in sorted(glob.glob(os.path.join(R, "data", "traces_*.js"))))
replay = json.dumps(open(os.path.join(R, "swarm_replay.html")).read()).replace("</", "<\\/")
tag = '<script src="data/lab.js"></script>'; assert tag in page
page = page.replace(tag, "<script>" + data + "\nwindow.SWARM_REPLAY_HTML = " + replay + ";</script>")
old = '<iframe src="swarm_replay.html"'; assert old in page
page = page.replace(old, '<iframe data-replay="1"')
page = page.replace("</body>", "<script>(function(){function fill(){document.querySelectorAll('iframe[data-replay]').forEach(function(f){if(!f.srcdoc){f.srcdoc=window.SWARM_REPLAY_HTML;}});}fill();new MutationObserver(fill).observe(document.body,{childList:true,subtree:true});})();</script></body>")
open(os.path.join(R, "standalone.html"), "w").write(page)
print("standalone.html", os.path.getsize(os.path.join(R, "standalone.html")) // 1024, "KB")
