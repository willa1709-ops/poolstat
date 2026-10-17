import requests, re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

url="https://sokolovna.bazenmb.cz/obsazenost-drah/"
r=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=20)
print("PAGE",r.status_code,len(r.text))
s=BeautifulSoup(r.text,"html.parser")

print("\nSCRIPT SRCS")
for tag in s.find_all("script"):
    src=tag.get("src")
    if src:
        print(urljoin(url,src))

print("\nINLINE HITS")
for i,tag in enumerate(s.find_all("script")):
    if tag.get("src"):
        continue
    txt=tag.string or tag.get_text()
    low=txt.lower()
    if any(k in low for k in ["ajax","data-value","ds_td_item","draha","obsazen","wp-json","admin-ajax"]):
        print("INLINE",i,re.sub(r"\s+"," ",txt)[:8000])

print("\nEXTERNAL JS HITS")
for tag in s.find_all("script"):
    src=tag.get("src")
    if not src:
        continue
    full=urljoin(url,src)
    try:
        rr=requests.get(full,headers={"User-Agent":"Mozilla/5.0"},timeout=20)
        low=rr.text.lower()
        if any(k in low for k in ["ds_td_item","data-value","draha","obsazen","admin-ajax","ajaxurl"]):
            print("JS",full,"status",rr.status_code,"bytes",len(rr.text))
            for key in ["ds_td_item","data-value","admin-ajax","ajaxurl","draha","obsazen"]:
                pos=low.find(key)
                if pos>=0:
                    print("HIT",key,re.sub(r"\s+"," ",rr.text[max(0,pos-1200):pos+4000]))
    except Exception as e:
        print("ERR",full,repr(e))
