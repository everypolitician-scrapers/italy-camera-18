# -*- coding: utf-8 -*-
from datetime import datetime
import locale
import re
import time
import os
import os.path

from bs4 import BeautifulSoup as bs
import requests
import scraperwiki


locale.setlocale(locale.LC_ALL,'it_IT.utf8')

term = "17"
base_url = "http://www.camera.it"
url_tmpl = base_url + "/leg17/313?current_page_2632={page}&shadow_deputato_has_sesso={gender}"
group_dict = {}
term_start_date = "2013-03-19"

def fetch_url(url, filename):
    if not os.environ.get("MORPH_ENV") and os.path.exists(os.path.join('cache', filename)):
        with open(os.path.join('cache', filename)) as f:
            r = f.read().decode('utf8')
    else:
        r = requests.get(url).text
        time.sleep(0.5)
        with open(os.path.join('cache', filename), 'w') as f:
            f.write(r.encode('utf8'))
    return r

def parse_dates(text):
    return [datetime.strptime("{} {} {}".format(*x), "%d %B %Y").strftime("%Y-%m-%d") for x in re.findall(ur'(\d+)\xb0?\s+([^ ]+)\s+(\d{4})', text)]

def scrape_person(url, id_):
    # print("Fetching: {}".format(url))
    r = fetch_url(url, "member-{}.html".format(id_))
    soup = bs(r, "html.parser")
    member = {}

    if soup.find("span", {"class": "external_source_error"}):
        return member

    email_button = soup.find("div", {"class": "buttonMail"})
    if email_button:
        email = email_button.a["href"].split('=')[-1]
        member["email"] = email if '@' in email else None

    bio_soup = soup.find("div", {"class": "datibiografici"})
    member["birth_date"] = parse_dates(bio_soup.text)[0]

    election_data_soup = soup.find("div", {"class": "datielettoriali"})
    section_titles = election_data_soup.find_all('h4')

    for section_title in section_titles:
        title_text = section_title.text.strip()
        content_text = unicode(section_title.next_sibling)
        if re.match(r"Elett(?:o|a) nella circoscrizione", title_text):
            area = content_text
            member["area_id"], member["area"] = re.search(r'([^\s]+) \(([^\)]+)\)', area).groups()
        elif title_text == "Lista di elezione":
            member["election_list"] = content_text
        elif re.match(r"Proclamat(?:o|a)", title_text):
            start_date = parse_dates(content_text)[0]
            if start_date > term_start_date:
                member["start_date"] = start_date

    groups = []
    groups_soup = soup.find(text=re.compile(r"al gruppo parlamentare"))
    if groups_soup:
        group_soups = groups_soup.find_next('ul').find_all('li')
        for group_soup in group_soups:
            group_str = group_soup.text.replace(u'\xa0', u' ')
            group_dates = parse_dates(group_str)
            group_name = re.match(ur"^(.*?)\s+dal(?: |l')\d", group_str, re.DOTALL).group(1)
            group_name = re.sub(r"\s\s*", " ", group_name)
            if group_name.lower() in group_dict:
                group_name = group_dict[group_name.lower()]
            else:
                group_dict[group_name.lower()] = group_name
            groups.append([group_name] + group_dates)

    member["groups"] = groups

    return member

def scrape_list(gender):
    data = []
    page = 0
    while True:
        page += 1
        url = url_tmpl.format(page=page, gender=gender)
        # print("Fetching: {}".format(url))
        r = fetch_url(url, "index-{}-{}.html".format(gender, page))
        soup = bs(r, "html.parser")
        members_ul = soup.find("ul", {"class": "main_img_ul"})
        if not members_ul:
            break
        member_lis = members_ul.find_all("li")
        for member_li in member_lis:
            id_ = member_li['id'][12:]
            end_date = member_li.find("div", {"class": "has_data_cessazione_mandato_parlamentare"})
            if end_date:
                end_date = re.search(r'\d{2}\.\d{2}\.\d{4}', end_date.text).group()
                end_date = "{}-{}-{}".format(end_date[6:], end_date[3:5], end_date[:2])
            url = base_url + "/leg17/" + member_li.a['href'].replace('\n', '')
            if url[-1] == "=":
                url += term
            member = scrape_person(url, id_)
            all_fields = {
                "id": id_,
                "birth_date": member.get("birth_date", ""),
                "area_id": member.get("area_id", ""),
                "area": member.get("area", ""),
                "start_date": member.get("start_date", ""),
                "end_date": end_date if end_date else "",
                "election_list": member.get("election_list", ""),
                "email": member.get("email", ""),
                "name": member_li.find("div", {"class": "nome_cognome_notorieta"}).text.strip(),
                "image": base_url + member_li.img['src'],
                "gender": "female" if gender == "F" else "male",
                "term": term,
                "source": url,
            }
            if member.get("groups", []) != []:
                for group in member["groups"]:
                    d = dict(all_fields)
                    d["group"] = group[0]
                    if group[1] > term_start_date:
                        d["start_date"] = group[1]
                    if len(group) == 3:
                        d["end_date"] = group[2]
                    data.append(d)
            else:
                data.append(all_fields)
    return data

data = []
for gender in ["F", "M"]:
    data += scrape_list(gender)

scraperwiki.sqlite.save(["id", "start_date"], data, "data")
