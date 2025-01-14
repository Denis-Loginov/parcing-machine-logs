import sys

import re
import threading
import os
import json

from flask import Flask, request, render_template
from datetime import datetime, date, timedelta
from striprtf.striprtf import rtf_to_text
from models import *
from db_create import *
from sqlalchemy import func, and_, desc

ARGS = sys.argv[1:]

if '-systemctl' in ARGS:
    import os
    путь_к_файлу = os.path.dirname(__file__)
    _body = f"""[Unit]
Description=CNC Logger

[Service]
WorkingDirectory={путь_к_файлу}/
ExecStart=python3.10 app.py 

[Install]
WantedBy=default.target"""
    
    with open(f'/etc/systemd/system/wvcrm-cnc-logger.service', "w") as f:
        f.write(_body)
    
    import subprocess
    subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
    subprocess.run(["sudo", "systemctl", "enable", f"wvcrm-cnc-logger.service"], check=True)
    subprocess.run(["sudo", "systemctl", "restart", f"wvcrm-cnc-logger.service"], check=True)
    sys.exit(0)

app = Flask(__name__)

def get_allowed_downtime_value():
    _ses = create_db1(db_config)
    try:
        allowed_downtime_value = _ses.query(settings_main.value).filter(settings_main.name == 'allowed_downtime').scalar()
        return int(allowed_downtime_value) * 60 if allowed_downtime_value else 120
    finally:
        _ses.close()

downtime = False
_pause_time = line_number = 0
last_processed_file = _datetime_start = _datetime_pause_start = id_value = _total_time_end = None
ALLOWED_DOWNTIME = get_allowed_downtime_value()


def convert_time_to_seconds(time_str):
    hours, minutes, seconds = 0, 0, 0

    hours_match = re.search(r'(\d+)\s*hours?', time_str)
    minutes_match = re.search(r'(\d+)\s*min', time_str)
    seconds_match = re.search(r'(\d+)\s*\.\d*s|\s(\d+)\s*s', time_str)

    if hours_match:
        hours = int(hours_match.group(1)) * 3600
    
    if minutes_match:
        minutes = int(minutes_match.group(1)) * 60
    
    if seconds_match:
        if seconds_match.group(1):
            seconds = int(seconds_match.group(1))
        elif seconds_match.group(2):
            seconds = int(seconds_match.group(2))

    total_seconds = hours + minutes + seconds

    return total_seconds

def extract_id_from_string(line):
    match = re.search(r'\/(\d+)\.lxd', line.replace('\\', '/'))
    if match:
        return match.group(1)
    return None

def extract_datetime_from_string(line):
    date_time_match = re.search(r'\((\d{2}/\d{2})\s(\d{2}:\d{2}:\d{2})\)', line)
    if date_time_match:
        date_str, time_str = date_time_match.groups()
        date_obj = datetime.strptime(date_str, '%m/%d')
        current_year = datetime.now().year
        date_obj = date_obj.replace(year=current_year)
        date_time_str = f"{date_obj.strftime('%Y-%m-%d')} {time_str}"
        return datetime.strptime(date_time_str, '%Y-%m-%d %H:%M:%S')
    return None

def extract_times_from_string(line):
    pattern = (
        r'Processing time \(estimated\):\s*([\dhoursmin.\d\s]+s),\s*'
        r'Move time\(estimated\):\s*([\dhoursmin.\d\s]+s),\s*'
        r'Delay Time:\s*([\dhoursmin.\d\s]+s),\s*'
        r'Total time \(estimated\):\s*([\dhoursmin.\d\s]+s)'
    )

    match = re.search(pattern, line)
    
    if match:
        processing_time_str = match.group(1)
        move_time_str = match.group(2)
        delay_time_str = match.group(3)
        total_time_str = match.group(4)
        
        processing_time = convert_time_to_seconds(processing_time_str)
        move_time = convert_time_to_seconds(move_time_str)
        delay_time = convert_time_to_seconds(delay_time_str)
        total_time_start = convert_time_to_seconds(total_time_str)
        
        return processing_time, move_time, delay_time, total_time_start
    return None, None, None, None

def extract_total_time_end_from_string(line):
    pattern = r'Spend time:\s*(\d*\s*hours)?(\d*\s*min)?(\d*\s*s)?'
    
    match = re.search(pattern, line)
    
    if match:
        hours_str = match.group(1) or ''
        minutes_str = match.group(2) or ''
        seconds_str = match.group(3) or ''
        
        total_time_end = convert_time_to_seconds(hours_str + minutes_str + seconds_str)
        
        return total_time_end

    return None

def current_settings_close(_ses, _datetime_start, laser_id):
    _current_settings = _ses.query(status_machine_logs).filter(status_machine_logs.status == 'settings', status_machine_logs.machine_id == laser_id, status_machine_logs.date_end.is_(None)).order_by(desc(status_machine_logs.date_start)).first()
    if _current_settings:
        _current_settings.date_end = _datetime_start
        _ses.commit()

def current_work_close(_ses, _datetime_end, _total_time_end, _pause_time, laser_id):
    _current_work = _ses.query(status_machine_logs).filter(status_machine_logs.status == 'work', status_machine_logs.machine_id == laser_id, status_machine_logs.date_end.is_(None)).order_by(desc(status_machine_logs.date_start)).first()
    if _current_work:
        _current_work.date_end = _datetime_end
        _current_work.total_time_end = _total_time_end
        _current_work.pause_time = _pause_time
        _ses.commit()

def get_current_user(_ses, _datetime_start_current, laser_id):
    _laser_list = _ses.query(task_complete, laser_park).outerjoin(
                task, task.id == task_complete.task_id).outerjoin(
                laser_production, laser_production.production_id == task.production_id).outerjoin(
                laser_power, laser_power.id == laser_production.laser_power_id).outerjoin(
                laser_machine, laser_machine.id == laser_production.laser_machine_id).outerjoin(
                laser_park, and_(laser_park.laser_id == laser_machine.id, laser_park.power_id == laser_power.id)).filter(
                func.DATE(task_complete.date_start) <= _datetime_start_current,
                laser_park.id == laser_id).order_by(
                desc(task_complete.date_start)).first()
    _current_user = _laser_list.task_complete.user_id
    return _current_user


def process_line(_ses, line, file_name, line_number, laser_id):
    global _datetime_pause_start, _datetime_pause_end, downtime, _pause_time, _datetime_start, id_value, _total_time_end

    # Проверяем, является ли строка пустой
    if not line.strip():
        return

    if downtime:
        _datetime_start_current = extract_datetime_from_string(line)
        if (_datetime_start_current-_datetime_start).total_seconds() > ALLOWED_DOWNTIME:
            _current_user = get_current_user(_ses, _datetime_start, laser_id)
            _new_record = status_machine_logs(None, 'Laser', laser_id, _current_user, _datetime_start, _datetime_start_current, None, None, None, None, None, None, 'downtime', file_name, line_number)
            _ses.add(_new_record)
            _ses.commit()
        _datetime_start = _datetime_start_current

    if '.lxd' in line:
        id_value = extract_id_from_string(line)
        _datetime_start = extract_datetime_from_string(line)
        if id_value and _datetime_start:
            current_settings_close(_ses, _datetime_start, laser_id)
            _current_user = get_current_user(_ses, _datetime_start, laser_id)
            _new_record = status_machine_logs(id_value, 'Laser', laser_id, _current_user, _datetime_start, None, None, None, None, None, None, None, 'settings', file_name, line_number)
            _ses.add(_new_record)
            _ses.commit()

    elif 'Processing time' in line:
        _datetime_start = extract_datetime_from_string(line)
        processing_time, move_time, delay_time, total_time_start = extract_times_from_string(line)
        if _datetime_start:
            current_settings_close(_ses, _datetime_start, laser_id)
            _current_user = get_current_user(_ses, _datetime_start, laser_id)
            _new_record = status_machine_logs(id_value, 'Laser', laser_id, _current_user, _datetime_start, None, processing_time, move_time, delay_time, total_time_start, None, None, 'work', file_name, line_number)
            _ses.add(_new_record)
            _ses.commit()
            _pause_time = 0
            downtime = False
    
    elif 'Processing End!' in line:
        _total_time_end = extract_total_time_end_from_string(line)
    
    elif '_*.g' in line:
        _datetime_start = extract_datetime_from_string(line)
        if _datetime_start:
            current_work_close(_ses, _datetime_start, _total_time_end, _pause_time, laser_id)
            _total_time_end = None
            _pause_time = 0
            downtime = True

    elif 'User stop' in line and not downtime:
        _datetime_pause_start = extract_datetime_from_string(line)
    
    elif re.search(r'\(\d{2}/\d{2} \d{2}:\d{2}:\d{2}\)Pause$', line.strip()) and not downtime:
        _datetime_pause_start = extract_datetime_from_string(line)
    
    elif 'Alarm:Tip Touch' in line and not downtime:
        _datetime_pause_start = extract_datetime_from_string(line)

    elif re.search(r'\(\d{2}/\d{2} \d{2}:\d{2}:\d{2}\)Resume$', line.strip()) and not downtime:
        _datetime_pause_end = extract_datetime_from_string(line)
        if _datetime_pause_start:
            _pause_time += (_datetime_pause_end - _datetime_pause_start).total_seconds()


@app.route('/upload', methods=['POST'])
def upload_file():
    global _datetime_pause_start, _datetime_pause_end, line_number, last_processed_file, _datetime_start, _pause_time, downtime

    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    
    laser_id = request.form.get('laser_id')
    if not laser_id:
        return 'No laser_id provided', 400
    
    try:
        # Прочитать содержимое файла в память
        file_content = file.read()
        # Преобразовать содержимое RTF в текст
        plain_text = rtf_to_text(file_content.decode('utf-8'))
        lines = plain_text.splitlines()

        _ses = create_db1(db_config)

        try:
            line_number = 0
            for line_number, line in enumerate(lines, start=1):
                process_line(_ses, line, file.filename, line_number, laser_id)
            
            return 'File successfully uploaded and processed', 200
        except Exception as e:
            return f'Error processing file lines: {e}', 500
        finally:
            _ses.close()
    
    except Exception as e:
        return f'Error reading file content: {e}', 500


@app.route('/')
def index():
    _ses = create_db1(db_config)
    
    try:
        today_start = datetime.combine(date.today(), datetime.min.time())
        now = datetime.now()
        status_machine_table = _ses.query(status_machine_logs).filter(
            status_machine_logs.date_start >= today_start,
            status_machine_logs.date_start <= now
        ).order_by(desc(status_machine_logs.date_start)).all()

        return render_template('work_machine_info.html', logs=status_machine_table)
    except Exception as ex:
        print(ex)
    finally:
        _ses.close()


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False, threaded=True)
