import requests, re
from bs4 import BeautifulSoup

url="https://sokolovna.bazenmb.cz/obsazenost-drah/"
r=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=20)
print("status",r.status_code,"bytes",len(r.content))
s=BeautifulSoup(r.text,"html.parser")

for i,table in enumerate(s.find_all("table")):
    print("\nTABLE",i,"class",table.get("class"),"id",table.get("id"))
    rows=table.find_all("tr")
    print("rows",len(rows))
    for ri,row in enumerate(rows[:8]):
        vals=[]
        for cell in row.find_all(["th","td"]):
            vals.append({
                "text":" ".join(cell.stripped_strings)[:80],
                "class":cell.get("class"),
                "style":cell.get("style"),
                "title":cell.get("title"),
                "data":{k:v for k,v in cell.attrs.items() if str(k).startswith("data-")}
            })
        print("ROW",ri,vals)

print("\nCSS/JS refs")
for tag in s.find_all(["link","script"]):
    src=tag.get("href") or tag.get("src")
    if src and ("obsazen" in src.lower() or "style" in src.lower() or "script" in src.lower() or "theme" in src.lower()):
        print(src)
