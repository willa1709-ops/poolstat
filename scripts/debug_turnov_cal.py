import requests, re
from datetime import datetime
from zoneinfo import ZoneInfo

ids=[
"bqettkjududod4avmcdn83pc44@group.calendar.google.com",
"f1rsuu7eiiiasjr9ula9siei4g@group.calendar.google.com",
"it9gt2cnsiq3vma7qcc9m029t4@group.calendar.google.com",
"kck840n1fbctjerc2ktlq0r24o@group.calendar.google.com",
]

for cid in ids:
    url="https://calendar.google.com/calendar/ical/"+requests.utils.quote(cid,safe="")+"/public/basic.ics"
    print("\n###",cid)
    try:
        r=requests.get(url,timeout=20,headers={"User-Agent":"Mozilla/5.0"})
        print("status",r.status_code,"bytes",len(r.content),"type",r.headers.get("content-type"))
        txt=r.text.replace("\r\n","\n")
        print(txt[:12000])
    except Exception as e:
        print("ERROR",repr(e))
