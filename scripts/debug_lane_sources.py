import re, requests
from bs4 import BeautifulSoup

URLS = {
    "jablonec": "https://jduplavat.cz/koupaliste/bazen-sport-jablonec-nad-nisou",
    "jicin": "https://jduplavat.cz/koupaliste/aqua-centrum-jicin",
    "hloubetin": "https://jduplavat.cz/koupaliste/plavecky-areal-hloubetin",
}

for name, url in URLS.items():
    print("\n###", name, url)
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        print("status", resp.status_code, "bytes", len(resp.content))
        soup = BeautifulSoup(resp.text, "html.parser")
        today = soup.select_one(".lane-day--today")
        if not today:
            print("NO TODAY")
            continue
        print("today id", today.find_parent(class_="accordion-collapse").get("id"))
        axis = [(x.get_text(" ",strip=True), x.get("style")) for x in today.select(".lane-tick")]
        print("axis", axis)
        rows = today.select(".lane-row:not(.lane-row--axis)")
        print("rows", len(rows))
        for row in rows:
            name_el=row.select_one(".lane-name")
            print("ROW", name_el.get_text(" ",strip=True) if name_el else "?")
            for el in row.select("[style]"):
                style=el.get("style","")
                if "left:" in style or "width:" in style:
                    print("SEG", {"class":el.get("class"),"style":style,"title":el.get("title"),"data_bs_title":el.get("data-bs-title"),"aria":el.get("aria-label"),"text":el.get_text(" ",strip=True)})
    except Exception as e:
        print("ERROR", repr(e))
