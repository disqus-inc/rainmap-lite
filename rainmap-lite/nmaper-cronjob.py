#!/usr/bin/python
#Cronjob script that executes Nmap scans on the background
import psycopg2
import os
import subprocess
import smtplib
import datetime
import uuid
import lxml.etree as ET
import distutils.spawn

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from NmapOptions import NmapOptions

#<CONFIGURATION>
BASE_URL = os.getenv('RAINMAP_DOMAIN', 'localhost')
SMTP_USER = os.getenv('RAINMAP_SMTP_USER')
SMTP_PASS = os.getenv('RAINMAP_SMTP_PASSWORD')
SMTP_SERVER = os.getenv('SMTP_HOST', 'localhost')
SMTP_PORT = 587
#</CONFIGURATION>

OUTPUT_PATH = os.path.normpath("%s/nmaper/static/results" % os.getcwd()).replace("\\", "/")

def find_nmap():
    if os.name == "nt":
        nmap_path = distutils.spawn.find_executable("nmap.exe", os.environ["PROGRAMFILES(X86)"]+"\\Nmap")
        if not(nmap_path):
            nmap_path = distutils.spawn.find_executable("nmap.exe", os.environ["PROGRAMFILES"]+"\\Nmap")
    else:
        nmap_path = distutils.spawn.find_executable("nmap","/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")

    return nmap_path

def notify(id_, email, cmd):
    print('[%s] Sending report %s to %s' % (datetime.datetime.now(), id_, email))
    msg = MIMEMultipart()
    msg['From'] = os.getenv('RAINMAP_FROM_MAIL', 'portscan@disqus.net')
    msg['To'] = email
    msg['Subject'] = "Your scan results are ready"
    body = "{2}\n\nView online:\n{0}/static/results/{1}.html\n\nDownload:\n{0}/static/results/{1}.nmap\n{0}/static/results/{1}.xml\n{0}/static/results/{1}.gnmap".format(BASE_URL, id_, cmd)
    msg.attach(MIMEText(body, 'plain'))
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.ehlo()
    server.starttls()
    server.ehlo()
    text = msg.as_string()
    server.sendmail(os.getenv('RAINMAP_FROM_MAIL', 'portscan@disqus.net'), email, text)

def update_status(id_, status, cursor, db):
    cursor.execute("UPDATE nmaper_nmapscan SET status_text = ? WHERE id = ? ", (status, id_))
    db.commit()
    print("[%s] Job #%s status changed to '%s'" % (datetime.datetime.now(), id_, status))

def set_random_id(id_, cursor, db):
    rid = uuid.uuid4()
    cursor.execute("UPDATE nmaper_nmapscan SET uuid = ? WHERE id = ? ", (rid.hex, id_))
    db.commit()
    return rid.hex

def set_endtime(id_, cursor, db):
    cursor.execute("UPDATE nmaper_nmapscan SET end_date = ? WHERE id = ? ", (datetime.datetime.now(), id_))
    db.commit()

def execute(path, cmd, uuid):
    filename  = "%s/%s" % (OUTPUT_PATH, uuid)
    nmap_cmd = '%s %s -oA %s' % (path, cmd, filename)
    ops = NmapOptions()
    ops.parse_string(nmap_cmd)
    proc = subprocess.Popen(ops.render(), shell=False)
    proc.wait()

    print('\n[%s] Finished execution of command "%s"' % (datetime.datetime.now(), cmd))

    dom = ET.parse("%s.xml" % filename)
    xsl_filename = dom.getroot().getprevious().getprevious().parseXSL() # need to add error checking
    transform = ET.XSLT(xsl_filename)
    html = transform(dom)
    html_file = open('%s.html' % filename, 'w')
    html.write(html_file)

    print('[%s] HTML report generated (%s.html)' % (datetime.datetime.now(), filename))

def main():
    path = find_nmap()
    if not path:
        print("[%s] Could not find path for nmap. Quitting!" % datetime.datetime.now())
        exit()

    db = psycopg2.connect(host=os.getenv('RAINMAP_POSTGRES_HOST', 'localhost'), database=os.getenv('RAINMAP_POSTGRES_PATH'), user=os.getenv('RAINMAP_DB_USER'), password=os.getenv('RAINMAP_DB_PASSWORD'))
    cursor = db.cursor()
    cursor.execute("SELECT * FROM nmaper_nmapscan WHERE status_text='waiting';")
    all_rows = cursor.fetchall()
    print('[%s] Listing pending nmap scans...' % datetime.datetime.now())

    for row in all_rows:
        cmd = row[2]
        jid = row[0]
        email = row[5]
        print('[%s] Job #%d:%s' % (datetime.datetime.now(), jid, cmd))
        rid = set_random_id(jid, cursor, db)
        update_status(jid, "running", cursor, db)
        execute(path, cmd, rid)
        update_status(jid, "finished", cursor, db)
        set_endtime(jid, cursor, db)
        print("[%s] Job #%d finished. Notifying '%s'" % (datetime.datetime.now(), jid, email))
        notify(rid, email, cmd)

if __name__ == "__main__":
    main()
