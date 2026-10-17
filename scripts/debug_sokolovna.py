import requests, json
from bs4 import BeautifulSoup

url="https://sokolovna.bazenmb.cz/obsazenost-drah/"
r=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=20)
s=BeautifulSoup(r.text,"html.parser")
el=s.select_one(".ds_week_data")
print("status",r.status_code,"found",bool(el))
if el:
    raw=el.get("value") or el.get_text()
    print("raw_len",len(raw))
    data=json.loads(raw)
    print("items",len(data))
    for x in data:
        print(json.dumps({
            "action_id":x.get("action_id"),
            "title":x.get("title"),
            "color":x.get("color"),
            "hours":x.get("hours"),
            "coordsT":x.get("coordsT")
        },ensure_ascii=False))
