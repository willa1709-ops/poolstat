import re, requests
from bs4 import BeautifulSoup

URLS = {
    "jablonec_isport": "https://sportjablonec.isportsystem.cz/",
    "jicin_isport": "https://sport-jicin.isportsystem.cz/?op=tab-id-44",
    "jablonec_jduplavat": "https://jduplavat.cz/koupaliste/bazen-sport-jablonec-nad-nisou",
    "hloubetin_jduplavat": "https://www.jduplavat.cz/koupaliste/plavecky-areal-hloubetin",
}

for name, url in URLS.items():
    print("\n###", name, url)
    r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
    print("status", r.status_code, "bytes", len(r.content), "final", r.url)
    html = r.text
    print("keywords", {k: html.lower().count(k) for k in ["dráha","draha","timeline","reservation","rezerv","left:","width:","data-start","data-end"]})
    soup = BeautifulSoup(html, "html.parser")
    shown = 0
    for tag in soup.find_all(True):
        attrs = " ".join(f"{k}={v}" for k,v in tag.attrs.items())
        txt = " ".join(tag.stripped_strings)
        hay = (attrs+" "+txt).lower()
        if any(k in hay for k in ["dráha","draha","timeline","reservation","rezerv","left:","width:","data-start","data-end"]):
            s = str(tag)
            print("TAG", re.sub(r"\s+", " ", s)[:1200])
            shown += 1
            if shown >= 25:
                break
